import json
import pytest
from taskforge import llm
from taskforge.config import ModelCfg, load_config


def test_config_loads_and_hash_is_40_chars():
    cfg = load_config("config.yaml")
    assert len(cfg.base_commit) == 40 and cfg.max_retries == 3


def test_bad_hash_rejected(tmp_path):
    text = open("config.yaml").read().replace(load_config("config.yaml").base_commit, "abc123")
    p = tmp_path / "c.yaml"
    p.write_text(text)
    with pytest.raises(ValueError):
        load_config(p)


def test_family_warning_when_same_family():
    cfg = load_config("config.yaml")
    cfg.models.critic = ModelCfg(provider="gemini", model="gemini-2.5-pro", api_key_env="X")
    assert llm.check_family(cfg) is not None


def test_mock_provider_logs_and_cycles(tmp_path):
    llm.set_run_dir(tmp_path)
    llm.set_mock_responses({"r": ["a", "b"]})
    m = ModelCfg(provider="mock", model="m")
    assert [llm.call_llm("r", "sys", "usr", m) for _ in range(3)] == ["a", "b", "b"]
    rows = [json.loads(x) for x in (tmp_path / "llm_log.jsonl").read_text().splitlines()]
    assert len(rows) == 3 and rows[0]["model"] == "m" and "prompt_hash" in rows[0]


def test_gemini_request_shape_and_no_key_in_log(monkeypatch, tmp_path):
    seen = {}

    def fake_post(url, headers, body, timeout=0):
        seen.update(url=url, headers=headers, body=body)
        return {"candidates": [{"content": {"parts": [{"text": "hi"}]}}],
                "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1}}

    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET123")
    llm.set_run_dir(tmp_path)
    m = ModelCfg(provider="gemini", model="gemini-x", api_key_env="GEMINI_API_KEY", rpm=0)
    assert llm.call_llm("r", "s", "u", m, json_mode=True) == "hi"
    assert seen["url"].endswith("/models/gemini-x:generateContent")
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert "SECRET123" not in (tmp_path / "llm_log.jsonl").read_text()


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    with pytest.raises(RuntimeError):
        llm.call_llm("r", "s", "u", ModelCfg(provider="gemini", model="g", api_key_env="NOPE_KEY", rpm=0))
