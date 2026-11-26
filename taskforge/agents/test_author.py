"""Test author: sees ONLY instruction.md (never the patch) -> tests/test_feature.py."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..gitutil import pytest_ids
from ..jsonutil import extract_code
from ..llm import call_llm

SYSTEM = """You write pytest tests for a click feature described ONLY by instruction.md. \
You have not seen the implementation. Rules:
- One behaviour per test function, named test_<behaviour>.
- Import the new public API INSIDE each test function (or use getattr(click, "Name", None)), never at the \
top of the file, so each test fails on its own when the feature is missing.
- Use click.testing.CliRunner or direct API calls. No network, no sleeps, no randomness, no time dependence.
- Check exact error messages ONLY where instruction.md states them exactly.
- Test nothing that instruction.md does not state. Cover every stated requirement, boundary and error.
Return ONLY the python file in a ```python block."""

TARGET = "tests/test_taskforge_feature.py"


def write_tests(cfg: Config, instruction: str, feedback: str = "", tag: str = "") -> str:
    user = (f"instruction.md:\n{instruction}\n"
            + (f"\nFix these problems from the previous attempt:\n{feedback}\n" if feedback else ""))
    return extract_code(call_llm("test_author", SYSTEM, user, cfg.models.main, tag=tag))


def feature_ids(wt: Path, test_code: str) -> tuple[list[str], dict[str, str], str]:
    """Run the feature file on the (patch-free) worktree. Returns (f2p ids, outcomes, output)."""
    (wt / TARGET).write_text(test_code)
    res, out = pytest_ids(wt, [TARGET, "--continue-on-collection-errors"])
    ids = sorted(i for i in res if i.startswith(TARGET))
    return ids, res, out


def build_p2p(baseline_tests: list[str]) -> list[str]:
    return [t for t in baseline_tests if not t.startswith(TARGET)]
