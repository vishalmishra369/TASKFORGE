"""Critic: independent model family, veto power over the spec/tests/patch triple."""
from __future__ import annotations

from ..config import Config
from ..jsonutil import extract_json
from ..llm import call_llm

SYSTEM = """You are a strict reviewer for a coding-agent benchmark. You get instruction.md (the only file \
the solver sees), the hidden tests, and the reference patch. Reject (approve=false) if ANY of:
1. a test checks behaviour or exact text that instruction.md does not state;
2. instruction.md is ambiguous, contradictory, or leaves a tested behaviour open;
3. the task is a bug fix rather than a new feature or changed behaviour;
4. the patch is trivially small or the tests are too weak to tell a correct from an incorrect solution;
5. the tests need network, randomness, sleeps, or credentials.
Return ONLY JSON: {"approve": true|false, "issues": ["specific, actionable issue", ...]}."""


def review(cfg: Config, instruction: str, tests: str, patch: str, tag: str = "") -> dict:
    user = f"instruction.md:\n{instruction}\n\nHidden tests:\n{tests}\n\nReference patch:\n{patch}\n"
    text = call_llm("critic", SYSTEM, user, cfg.models.critic, json_mode=True, tag=tag)
    try:
        d = extract_json(text)
        return {"approve": bool(d.get("approve")), "issues": list(d.get("issues", []))}
    except Exception as ex:  # an unreadable verdict is a rejection, never a silent approval
        return {"approve": False, "issues": [f"critic output unreadable: {ex}"]}
