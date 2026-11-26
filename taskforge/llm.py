"""One wrapper for every model call. Providers: gemini, ollama, openai(-compatible), anthropic, mock.

- Keys come ONLY from environment variables (never written to files/logs).
- Every call is logged to runs/<run_id>/llm_log.jsonl (prompt, response, model, tokens, latency).
- Self-throttles to cfg.rpm and retries 429/5xx with backoff (Gemini free tier needs this).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

import httpx

from .config import Config, ModelCfg


class LLMError(RuntimeError):
    """A model call failed or returned nothing usable. The orchestrator treats it as a failed try and retries."""


_LOCK = threading.Lock()
_LAST_CALL: dict[str, float] = {}
_RUN_DIR: Path | None = None
_MOCK_RESPONSES: dict = {}
_MOCK_COUNTER: dict[str, int] = {}


def set_run_dir(path: Path) -> None:
    global _RUN_DIR
    _RUN_DIR = Path(path)
    _RUN_DIR.mkdir(parents=True, exist_ok=True)


def set_mock_responses(responses: dict) -> None:
    """role -> str | list[str] (cycled). Used by tests and offline demos."""
    _MOCK_RESPONSES.clear()
    _MOCK_RESPONSES.update(responses)
    _MOCK_COUNTER.clear()


def prompt_hash(system: str) -> str:
    return hashlib.sha256(system.encode()).hexdigest()[:12]


def _throttle(key: str, rpm: int) -> None:
    if rpm <= 0:
        return
    gap = 60.0 / rpm
    with _LOCK:
        wait = _LAST_CALL.get(key, 0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL[key] = time.monotonic()


def _key(m: ModelCfg) -> str:
    if not m.api_key_env:
        return ""
    k = os.environ.get(m.api_key_env, "")
    if not k:
        raise LLMError(f"Environment variable {m.api_key_env} is not set")
    return k


def _post(url: str, headers: dict, body: dict, timeout: float = 300.0) -> dict:
    for attempt in range(6):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=timeout)
        except httpx.TransportError:
            time.sleep(2**attempt)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 4 * 2**attempt))
            continue
        if r.status_code >= 400:
            # never include headers (keys) in the error
            raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:500]}")
        return r.json()
    raise LLMError("LLM request failed after retries (rate limit or network)")


def _gemini(m: ModelCfg, system: str, user: str, json_mode: bool) -> tuple[str, int, int]:
    base = m.base_url or "https://generativelanguage.googleapis.com"
    url = f"{base}/v1beta/models/{m.model}:generateContent"
    gen = {"temperature": m.temperature}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen,
    }
    d = _post(url, {"x-goog-api-key": _key(m), "Content-Type": "application/json"}, body)
    u = d.get("usageMetadata", {})
    cands = d.get("candidates") or []
    if not cands:
        reason = (d.get("promptFeedback") or {}).get("blockReason", "no candidates returned")
        raise LLMError(f"Gemini returned no answer ({reason}); retry or rephrase")
    cand = cands[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    finish = cand.get("finishReason", "")
    if finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        raise LLMError(f"Gemini blocked the answer (finishReason={finish})")
    if finish == "MAX_TOKENS":
        raise LLMError("Gemini answer was cut off (MAX_TOKENS); ask for a smaller change")
    return text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def _ollama(m: ModelCfg, system: str, user: str, json_mode: bool) -> tuple[str, int, int]:
    base = m.base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    body = {
        "model": m.model,
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": m.temperature, "num_ctx": 16384},
    }
    if json_mode:
        body["format"] = "json"
    d = _post(f"{base}/api/chat", {}, body, timeout=900.0)
    text = (d.get("message") or {}).get("content", "")
    if not text.strip():
        raise LLMError("Ollama returned empty content")
    return text, d.get("prompt_eval_count", 0), d.get("eval_count", 0)


def _openai(m: ModelCfg, system: str, user: str, json_mode: bool) -> tuple[str, int, int]:
    base = (m.base_url or "https://api.openai.com/v1").rstrip("/")
    body = {
        "model": m.model,
        "temperature": m.temperature,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {_key(m)}"} if m.api_key_env else {}
    d = _post(f"{base}/chat/completions", headers, body, timeout=900.0)
    u = d.get("usage", {})
    choices = d.get("choices") or []
    text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
    if not text.strip():
        raise LLMError("OpenAI-compatible server returned empty content")
    return text, u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


def _anthropic(m: ModelCfg, system: str, user: str, json_mode: bool) -> tuple[str, int, int]:
    body = {
        "model": m.model,
        "max_tokens": 8000,
        "temperature": m.temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {"x-api-key": _key(m), "anthropic-version": "2023-06-01"}
    d = _post("https://api.anthropic.com/v1/messages", headers, body)
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise LLMError("Anthropic returned empty text")
    u = d.get("usage", {})
    return text, u.get("input_tokens", 0), u.get("output_tokens", 0)


def _mock(role: str) -> tuple[str, int, int]:
    r = _MOCK_RESPONSES.get(role)
    if r is None:
        raise RuntimeError(f"no mock response for role {role!r}")
    if isinstance(r, list):
        with _LOCK:
            i = _MOCK_COUNTER.get(role, 0)
            _MOCK_COUNTER[role] = i + 1
        r = r[min(i, len(r) - 1)]
    return r, 0, 0


PROVIDERS = {"gemini": _gemini, "ollama": _ollama, "openai": _openai, "anthropic": _anthropic}


def call_llm(role: str, system: str, user: str, model: ModelCfg, json_mode: bool = False,
             tag: str = "") -> str:
    """role = agent name (proposer, spec_writer, ...). tag = e.g. task id, for the log."""
    t0 = time.time()
    if model.provider == "mock":
        text, tin, tout = _mock(role)
    else:
        fn = PROVIDERS.get(model.provider)
        if fn is None:
            raise ValueError(f"unknown provider {model.provider!r}")
        _throttle(f"{model.provider}:{model.model}", model.rpm)
        try:
            text, tin, tout = fn(model, system, user, json_mode)
        except (KeyError, IndexError, TypeError, ValueError) as ex:
            raise LLMError(f"unexpected response shape from {model.provider}: {ex!r}") from ex
        if not text or not text.strip():
            raise LLMError(f"empty answer from {model.provider}/{model.model}")
    if _RUN_DIR is not None:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "role": role, "tag": tag,
            "provider": model.provider, "model": model.model,
            "prompt_hash": prompt_hash(system), "system": system, "user": user,
            "response": text, "tokens_in": tin, "tokens_out": tout,
            "latency_s": round(time.time() - t0, 2),
        }
        with _LOCK, open(_RUN_DIR / "llm_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    return text


def check_family(cfg: Config) -> str | None:
    """Warn if critic and main share a model family (breaks the 'independent critic' rule)."""
    if cfg.models.main.family == cfg.models.critic.family:
        return (f"critic ({cfg.models.critic.model}) is the same family as main "
                f"({cfg.models.main.model}); the deck promises a different family.")
    return None
