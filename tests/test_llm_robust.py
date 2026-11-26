import pytest

from taskforge import llm
from taskforge.config import ModelCfg

M = ModelCfg(provider="gemini", model="g", api_key_env="K", rpm=0)


def _call(monkeypatch, response):
    monkeypatch.setenv("K", "x")
    monkeypatch.setattr(llm, "_post", lambda *a, **k: response)
    return llm.call_llm("r", "s", "u", M)


@pytest.mark.parametrize("resp,needle", [
    ({"promptFeedback": {"blockReason": "SAFETY"}}, "SAFETY"),
    ({"candidates": []}, "no answer"),
    ({"candidates": [{"finishReason": "SAFETY"}]}, "blocked"),
    ({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{par"}]}}]}, "cut off"),
    ({"candidates": [{"content": {"parts": [{"text": "   "}]}}]}, "empty"),
    ({"candidates": [{"content": {}}]}, "empty"),
])
def test_gemini_failures_raise_llmerror(monkeypatch, resp, needle):
    with pytest.raises(llm.LLMError) as e:
        _call(monkeypatch, resp)
    assert needle in str(e.value)


def test_gemini_ok(monkeypatch):
    ok = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "hello"}]}}]}
    assert _call(monkeypatch, ok) == "hello"


def test_llmerror_is_runtimeerror():
    assert issubclass(llm.LLMError, RuntimeError)
