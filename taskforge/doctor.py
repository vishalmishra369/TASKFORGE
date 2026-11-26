"""`taskforge doctor`: check this machine before a run. Never prints secrets."""
from __future__ import annotations

import os
import shutil
import sys

import httpx

from . import llm
from .config import Config
from .gitutil import run


def _cmd(args: list[str]) -> tuple[bool, str]:
    if shutil.which(args[0]) is None:
        return False, f"{args[0]} not found on PATH"
    try:
        p = run(args, timeout=60)
    except Exception as ex:  # timeout, permission, etc.
        return False, str(ex)[:120]
    text = (p.stdout or "").strip() or (p.stderr or "").strip()
    first = text.splitlines()[0][:120] if text else ""   # empty / whitespace-only output is normal on Windows
    return p.returncode == 0, first


def _ollama_models(base: str) -> list[str] | None:
    try:
        r = httpx.get(f"{base.rstrip('/')}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None


def run_checks(cfg: Config) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    out.append(("python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0]))
    if os.name == "nt":
        out.append(("platform", True, "Windows: unit tests, review and export work here; run the full pipeline "
                                       "(`taskforge run`, Docker, Harbor) inside WSL2"))
    ok, d = _cmd(["git", "--version"])
    out.append(("git", ok, d))
    ok, d = _cmd(["docker", "info", "--format", "{{.ServerVersion}}"])
    out.append(("docker daemon running", ok, d if ok else d or "start Docker Desktop / the docker service"))
    ok, d = _cmd(["harbor", "--version"])
    out.append(("harbor 0.25.x", ok and d.startswith("0.25"), d or "pip install 'harbor==0.25.*'"))
    seen = set()
    for role in ("main", "critic"):
        m = getattr(cfg.models, role)
        if m.api_key_env and m.api_key_env not in seen:
            seen.add(m.api_key_env)
            out.append((f"{role}: env var {m.api_key_env}", bool(os.environ.get(m.api_key_env)),
                        "set" if os.environ.get(m.api_key_env) else "missing (put it in .env and export it)"))
        if m.provider == "ollama":
            base = m.base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            tags = _ollama_models(base)
            if tags is None:
                out.append((f"{role}: ollama reachable", False, f"cannot reach {base} (run `ollama serve`)"))
            else:
                have = any(t == m.model or t.split(":")[0] == m.model.split(":")[0] and ":" not in m.model for t in tags)
                out.append((f"{role}: model {m.model} pulled", have,
                            "ok" if have else f"run: ollama pull {m.model}"))
    warn = llm.check_family(cfg)
    out.append(("critic is a different model family", warn is None, warn or cfg.models.critic.family))
    return out
