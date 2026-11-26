"""Small git + pytest helpers. Everything runs on a throwaway git worktree of click at base_commit."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


def run(cmd: list[str], cwd: str | Path | None = None, env: dict | None = None,
        timeout: int = 1800, check: bool = False) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({p.returncode}):\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return p


@contextmanager
def worktree(repo: Path, commit: str):
    """Fresh detached worktree of `repo` at `commit`; removed on exit."""
    tmp = Path(tempfile.mkdtemp(prefix="tf_wt_"))
    wt = tmp / "click"
    run(["git", "worktree", "add", "--detach", str(wt), commit], cwd=repo, check=True)
    try:
        yield wt
    finally:
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=repo)
        shutil.rmtree(tmp, ignore_errors=True)


def apply_patch(wt: Path, patch_text: str) -> tuple[bool, str]:
    pf = wt.parent / "p.patch"
    pf.write_text(patch_text)
    p = run(["git", "apply", "--whitespace=nowarn", str(pf)], cwd=wt)
    return p.returncode == 0, (p.stderr or p.stdout).strip()


def diff(wt: Path, exclude_tests: bool = True) -> str:
    """git diff of tracked + new files, tests/ excluded (the solution must not touch tests)."""
    run(["git", "add", "-N", "."], cwd=wt)
    args = ["git", "diff", "--no-color"]
    if exclude_tests:
        args += ["--", ".", ":(exclude)tests"]
    return run(args, cwd=wt).stdout


def pytest_ids(wt: Path, targets: list[str], extra_env: dict | None = None,
               timeout: int = 900) -> tuple[dict[str, str], str]:
    """Run pytest in wt on targets, return ({nodeid: outcome}, raw output). Uses wt/src on PYTHONPATH."""
    out = wt.parent / "report.json"
    if out.exists():
        out.unlink()
    env = {"PYTHONPATH": str(wt / "src")}
    env.update(extra_env or {})
    p = run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
             "--json-report", f"--json-report-file={out}", *targets], cwd=wt, env=env, timeout=timeout)
    try:
        rep = json.loads(out.read_text())
        res = {t["nodeid"]: t["outcome"] for t in rep.get("tests", [])}
        # collection errors show up as "collectors" with outcome failed
        for c in rep.get("collectors", []):
            if c.get("outcome") == "failed" and c.get("nodeid"):
                res.setdefault(c["nodeid"], "failed")
    except Exception:
        res = {}
    return res, (p.stdout + p.stderr)[-6000:]
