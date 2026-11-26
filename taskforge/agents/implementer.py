"""Implementer: instruction.md + source files -> edits applied to a fresh worktree -> solution.patch."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from ..fsutil import write_lf
from ..config import Config
from ..gitutil import diff
from ..jsonutil import extract_json
from ..llm import call_llm

SYSTEM = """You are a senior maintainer of the Python library `click`. Implement the feature described in \
instruction.md by editing the given source files. Follow click's existing style, add docstrings, update \
__init__.py exports if a public name is added, and NEVER touch the tests/ directory. \
Keep the change small and focused; do not refactor unrelated code. Existing behaviour must not change.
Return ONLY JSON: {"edits":[{"path","search","replace"}],"new_files":[{"path","content"}]}.
`search` must be an EXACT, UNIQUE substring of the current file (include 2-3 lines of context). \
To append to a file, use the last lines of the file as `search` and repeat them in `replace`."""


SYSTEM_WHOLE = """You are a senior maintainer of the Python library `click`. Implement the feature described in \
instruction.md. Your previous search/replace edits could not be applied, so this time return the COMPLETE new \
content of every file you change. Keep all unrelated code byte-for-byte identical, follow click's style, add \
docstrings, update __init__.py exports if a public name is added, and NEVER touch tests/.
Return ONLY JSON: {"files":[{"path","content"}]}."""


MAX_PATCH_LINES = 450


def _read_context(wt: Path, paths: list[str], limit: int = 60000) -> str:
    chunks, used = [], 0
    for rel in dict.fromkeys(paths + ["src/click/__init__.py"]):
        f = wt / rel
        if f.is_file() and f.suffix == ".py":
            t = f.read_text(encoding="utf-8")
            if used + len(t) > limit:
                t = t[: max(0, limit - used)]
            used += len(t)
            chunks.append(f"=== {rel} ===\n{t}")
    return "\n\n".join(chunks)


def apply_edits(wt: Path, data: dict) -> str | None:
    """Apply search/replace edits. Returns an error string, or None on success."""
    for e in data.get("edits", []):
        rel = e["path"]
        if rel.startswith("tests/") or rel.startswith("/"):
            return f"edit refused: {rel} (never touch tests/)"
        f = wt / rel
        if not f.is_file():
            return f"edit target missing: {rel}"
        t = f.read_text(encoding="utf-8")
        if t.count(e["search"]) != 1:
            return f"search text in {rel} matches {t.count(e['search'])} times (need exactly 1): {e['search'][:120]!r}"
        write_lf(f, t.replace(e["search"], e["replace"]))
    for nf in data.get("new_files", []):
        rel = nf["path"]
        if rel.startswith("tests/") or rel.startswith("/"):
            return f"new file refused: {rel}"
        p = wt / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        write_lf(p, nf["content"])
    for f in {e["path"] for e in data.get("edits", [])} | {n["path"] for n in data.get("new_files", [])}:
        if f.endswith(".py"):
            try:
                ast.parse((wt / f).read_text(encoding="utf-8"))
            except SyntaxError as ex:
                return f"syntax error in {f}: {ex}"
    return None


def reset_worktree(wt: Path) -> None:
    """Undo every change in the worktree (used before the whole-file fallback)."""
    from ..gitutil import run
    run(["git", "checkout", "--", "."], cwd=wt)
    run(["git", "clean", "-fdq"], cwd=wt)


def apply_whole_files(wt: Path, data: dict) -> str | None:
    """Fallback format: full replacement content per file. Same safety rules as apply_edits."""
    files = data.get("files", [])
    if not files:
        return "whole-file answer contained no files"
    return apply_edits(wt, {"edits": [], "new_files": files})


def implement(cfg: Config, wt: Path, candidate: dict, instruction: str, feedback: str = "",
              tag: str = "") -> tuple[str | None, str | None]:
    """Returns (patch_text, error). The worktree must be fresh (at base_commit).

    Strategy: exact search/replace edits first (small output, easy to review). If they cannot be applied
    (search text mismatch, invalid JSON, syntax error) the same try falls back ONCE to whole-file output.
    """
    ctx = _read_context(wt, candidate.get("files_touched", []))
    user = (f"instruction.md:\n{instruction}\n\nSource files:\n{ctx}\n"
            + (f"\nFix these problems from the previous attempt:\n{feedback}\n" if feedback else ""))
    text = call_llm("implementer", SYSTEM, user, cfg.models.main, json_mode=True, tag=tag)
    err: str | None
    try:
        err = apply_edits(wt, extract_json(text))
    except ValueError as ex:
        err = f"implementer returned invalid JSON: {ex}"
    if err:  # fallback: whole files
        reset_worktree(wt)
        user2 = user + f"\nYour edit-based answer failed with: {err}\nReturn whole files instead."
        text2 = call_llm("implementer_whole", SYSTEM_WHOLE, user2, cfg.models.main, json_mode=True, tag=tag)
        try:
            err2 = apply_whole_files(wt, extract_json(text2))
        except ValueError as ex:
            err2 = f"whole-file answer invalid JSON: {ex}"
        if err2:
            reset_worktree(wt)
            return None, f"{err} | fallback also failed: {err2}"
    patch = diff(wt)
    if not patch.strip():
        return None, "implementer produced an empty patch"
    changed = sum(1 for ln in patch.splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---"))
    if changed > MAX_PATCH_LINES:
        return None, (f"patch changes {changed} lines (limit {MAX_PATCH_LINES}); keep the change focused and "
                      "do not reformat or rewrite unrelated code")
    return patch, None
