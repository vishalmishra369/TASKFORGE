"""Spec writer: candidate -> instruction.md (the ONLY file the solver sees)."""
from __future__ import annotations

import json

from ..config import Config
from ..llm import call_llm
from ..jsonutil import extract_code

SYSTEM = """You write instruction.md for a coding-agent benchmark task, like a real feature request \
to the open-source library `click`. Use exactly these sections:
# <Title>
## Background   (2-3 lines: why a CLI author wants this)
## Requirements (numbered, each independently testable: API signature, accepted inputs, return type, defaults)
## Errors       (exact conditions and the EXACT message text, in code formatting)
## Examples     (2-3 short CLI/Python snippets with the expected output)
## Out of scope (what must NOT change)
Rules: state every behaviour a hidden test could check. Never mention tests, test files, patches, \
graders or hidden details. Existing click behaviour must stay unchanged unless the spec says otherwise. \
Output only the markdown document."""


def write_spec(cfg: Config, candidate: dict, summary: str, feedback: str = "", tag: str = "") -> str:
    user = (f"Candidate feature:\n{json.dumps(candidate, indent=1)}\n\nRepo summary:\n{summary[:6000]}\n"
            + (f"\nFix these problems from the previous attempt:\n{feedback}\n" if feedback else ""))
    text = call_llm("spec_writer", SYSTEM, user, cfg.models.main, tag=tag)
    return extract_code(text, "markdown") if "```" in text and text.lstrip().startswith("```") else text.strip() + "\n"
