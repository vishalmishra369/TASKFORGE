"""Proposer: archetype + repo summary -> candidate features (JSON)."""
from __future__ import annotations

from ..config import Config
from ..jsonutil import extract_json
from ..llm import call_llm

SYSTEM = """You design FEATURE-DEVELOPMENT tasks for a benchmark that evaluates AI coding agents on the \
Python library `click`. You propose NEW features that do not exist in click (any version). \
Never propose bug fixes. Each feature must fit in one patch of 40-300 changed lines, need no network, \
no credentials, no randomness or timing, and be fully testable with click.testing.CliRunner or direct API calls.
Return ONLY a JSON object: {"candidates":[{"title","user_story","api_sketch","behaviours":[...],\
"edge_cases":[...],"files_touched":["src/click/..."],"est_lines":int,"new_names":[...]}]}.
`new_names` = the distinctive identifiers the feature introduces (class names, keyword-argument names, \
function names). `behaviours` = concrete, testable behaviours with exact error text where relevant."""


def propose(cfg: Config, archetype: dict, summary: str, avoid: list[str], n: int = 2, tag: str = "") -> list[dict]:
    user = (
        f"Archetype: {archetype['id']}\nDescription: {archetype['description']}\n"
        f"Archetype rules: {archetype['rules']}\nExample (do NOT reuse): {archetype['example']}\n\n"
        f"Already proposed or existing, avoid overlap: {avoid}\n\n"
        f"Repository summary:\n{summary}\n\nPropose {n} different candidate features."
    )
    text = call_llm("proposer", SYSTEM, user, cfg.models.main, json_mode=True, tag=tag)
    data = extract_json(text)
    cands = data["candidates"] if isinstance(data, dict) else data
    for c in cands:
        c["archetype"] = archetype["id"]
    return cands[:n]
