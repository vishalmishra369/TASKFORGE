"""Step 1-2: pin the commit, prove the baseline, and record which tests are stable.

Findings from testing on click 8.5.1: some tests (e.g. tests/test_utils/test_echo_via_pager.py)
depend on `less`/a TTY and fail in bare sandboxes. We therefore:
  * run the suite `baseline_repeats` times,
  * pass_to_pass = tests that PASSED in every run,
  * everything else is written to baseline_excluded.json (so it is logged, never hidden).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import Config
from .gitutil import run

TEMPLATES = Path(__file__).parent / "templates"


def render_dockerfile(cfg: Config) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), keep_trailing_newline=True)
    return env.get_template("Dockerfile.j2").render(repo_url=cfg.repo_url, base_commit=cfg.base_commit)


def clone_and_pin(cfg: Config) -> Path:
    wd = cfg.p(cfg.work_dir)
    if not (wd / ".git").exists():
        wd.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", cfg.repo_url, str(wd)], check=True)
    run(["git", "fetch", "--tags", "-q"], cwd=wd)
    run(["git", "checkout", "-q", cfg.base_commit], cwd=wd, check=True)
    head = run(["git", "rev-parse", "HEAD"], cwd=wd, check=True).stdout.strip()
    if head != cfg.base_commit or len(head) != 40:
        raise RuntimeError(f"HEAD {head} != base_commit {cfg.base_commit}")
    tag_commit = run(["git", "rev-list", "-n", "1", cfg.tag], cwd=wd).stdout.strip()
    if tag_commit and tag_commit != cfg.base_commit:
        raise RuntimeError(f"tag {cfg.tag} points to {tag_commit}, not base_commit {cfg.base_commit}")
    return wd


def _report_ids(path: Path) -> dict[str, str]:
    rep = json.loads(path.read_text())
    return {t["nodeid"]: t["outcome"] for t in rep.get("tests", [])}


def _pytest_local(wd: Path, out: Path) -> dict[str, str]:
    run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "--json-report",
         f"--json-report-file={out}", "tests"], cwd=wd, env={"PYTHONPATH": str(wd / "src")}, timeout=3600)
    return _report_ids(out)


def _pytest_docker(image: str, out_dir: Path, name: str) -> dict[str, str]:
    run(["docker", "run", "--rm", "-v", f"{out_dir.resolve()}:/out", image, "python", "-m", "pytest",
         "-p", "no:cacheprovider", "-q", "--json-report", f"--json-report-file=/out/{name}", "tests"],
        timeout=3600)
    return _report_ids(out_dir / name)


def run_baseline(cfg: Config, run_dir: Path, use_docker: bool = True) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    wd = clone_and_pin(cfg)
    results: list[dict[str, str]] = []
    image = None
    if use_docker:
        envdir = run_dir / "baseline_env"
        envdir.mkdir(exist_ok=True)
        (envdir / "Dockerfile").write_text(render_dockerfile(cfg))
        image = f"taskforge-baseline:{cfg.base_commit[:12]}"
        run(["docker", "build", "-t", image, str(envdir)], check=True, timeout=3600)
    for i in range(cfg.baseline_repeats):
        name = f"baseline_run{i + 1}.json"
        results.append(_pytest_docker(image, run_dir, name) if use_docker else _pytest_local(wd, run_dir / name))
    all_ids = sorted(set().union(*results))
    stable = [t for t in all_ids if all(r.get(t) == "passed" for r in results)]
    excluded = {t: [r.get(t, "missing") for r in results] for t in all_ids if t not in set(stable)}
    summary = {
        "base_commit": cfg.base_commit, "tag": cfg.tag, "docker": use_docker,
        "runs": len(results), "total_seen": len(all_ids), "stable_passing": len(stable),
        "excluded": len(excluded),
    }
    (run_dir / "baseline_tests.json").write_text(json.dumps(stable, indent=1))
    (run_dir / "baseline_excluded.json").write_text(json.dumps(excluded, indent=1))
    (run_dir / "baseline_summary.json").write_text(json.dumps(summary, indent=1))
    if not stable:
        raise RuntimeError("baseline: no stable passing tests; environment is broken")
    return summary
