"""Human sign-off before export (the deck's 'Human review before export').

State lives in tasks/<id>/manifest.json under the key "review":
  {"status": "approved"|"rejected", "by": name, "note": text, "at": timestamp}
`taskforge export` refuses tasks that are not approved (unless --allow-unreviewed).
"""
from __future__ import annotations

from .fsutil import write_lf

import hashlib
import json
import time
from pathlib import Path


def _mpath(task_dir: Path) -> Path:
    return task_dir / "manifest.json"


def load_manifest(task_dir: Path) -> dict | None:
    try:
        return json.loads(_mpath(task_dir).read_text(encoding="utf-8"))
    except Exception:
        return None


def content_hashes(task_dir: Path) -> dict:
    """sha256 of the three files a reviewer actually reads."""
    def h(rel: str) -> str:
        f = task_dir / rel
        return hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else ""
    return {"instruction": h("instruction.md"), "patch": h("solution/solution.patch"),
            "tests": h("tests/test_feature.py")}


def status(task_dir: Path) -> str:
    """pending | approved | rejected | stale (approved, but files changed after sign-off) | no-manifest."""
    m = load_manifest(task_dir)
    if m is None:
        return "no-manifest"
    r = m.get("review") or {}
    st = r.get("status", "pending")
    if st == "approved" and r.get("hashes") and r["hashes"] != content_hashes(task_dir):
        return "stale"
    return st


def set_review(task_dir: Path, decision: str, by: str, note: str = "") -> None:
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")
    m = load_manifest(task_dir)
    if m is None:
        raise FileNotFoundError(f"{task_dir.name} has no manifest.json (only generated tasks can be reviewed)")
    m["review"] = {"status": decision, "by": by, "note": note, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "hashes": content_hashes(task_dir)}
    write_lf(_mpath(task_dir), json.dumps(m, indent=1))


def review_card(task_dir: Path) -> str:
    """Plain-text summary a human reads before approving."""
    m = load_manifest(task_dir) or {}
    g = m.get("gates", {})
    mut = m.get("mutation", {})
    lines = [
        f"TASK        {task_dir.name}  ({m.get('archetype')})",
        f"TITLE       {m.get('title')}",
        f"GATES       " + (", ".join(f"{k}={'PASS' if v.get('pass') else 'FAIL'}" for k, v in g.items())
                           or ("harbor skipped" if m.get("harbor_skipped") else "none recorded")),
        f"MUTATION    {mut.get('kill_rate', 0):.0%} killed ({mut.get('killed')}/{mut.get('valid')}, {mut.get('runner')})",
        f"CRITIC      approve={m.get('critic', {}).get('approve')}  issues={m.get('critic', {}).get('issues')}",
        f"RETRIES     {m.get('retries')}   F2P={m.get('f2p_count')}  P2P={m.get('p2p_count')}",
        f"REVIEW      {status(task_dir)}",
        "",
        "CHECKLIST: feature really absent from click upstream? instruction.md states every tested behaviour and exact",
        "error text? no network/credentials in tests? different behaviour from the other 4 tasks?",
        f"Read: {task_dir}/instruction.md, {task_dir}/tests/test_feature.py, {task_dir}/solution/solution.patch",
    ]
    return "\n".join(lines)


def unapproved(tasks_dir: Path) -> list[str]:
    return [d.name for d in sorted(tasks_dir.iterdir())
            if d.is_dir() and not d.name.startswith("_") and status(d) != "approved"]
