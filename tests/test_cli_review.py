import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from taskforge import review as rv
from taskforge.cli import app

runner = CliRunner()


@pytest.fixture()
def proj(tmp_path):
    shutil.copy("config.yaml", tmp_path / "config.yaml")
    (tmp_path / "evidence").mkdir()
    t = tmp_path / "tasks" / "click-demo"
    for rel, txt in {"instruction.md": "# spec", "solution/solution.patch": "diff", "tests/test_feature.py": "x"}.items():
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / rel).write_text(txt)
    (t / "manifest.json").write_text(json.dumps({
        "task_id": "click-demo", "archetype": "new_param_type", "title": "Demo", "gates": {},
        "mutation": {"kill_rate": 0.9, "killed": 9, "valid": 10, "runner": "local"},
        "critic": {"approve": True, "issues": []}, "retries": 0, "review": None}))
    (tmp_path / "tasks" / "_golden").mkdir()
    return tmp_path


def run(proj, *args):
    return runner.invoke(app, [*args, "--config", str(proj / "config.yaml")])


def test_help_lists_all_commands():
    out = runner.invoke(app, ["--help"]).output
    for cmd in ("init", "generate", "validate", "export", "run", "review", "doctor", "baseline", "llm-check",
                "harbor-probe"):
        assert cmd in out


def test_export_blocked_until_reviewed_then_works_and_skips_golden(proj):
    r = run(proj, "export", "--out", str(proj / "dist"))
    assert r.exit_code == 1 and "click-demo" in r.output
    r = run(proj, "review", str(proj / "tasks/click-demo"), "--approve", "--by", "Vinayak", "--note", "ok")
    assert r.exit_code == 0 and rv.status(proj / "tasks/click-demo") == "approved"
    r = run(proj, "export", "--out", str(proj / "dist"))
    assert r.exit_code == 0
    assert (proj / "dist/tasks/click-demo/manifest.json").exists()
    assert not (proj / "dist/tasks/_golden").exists()
    assert (proj / "dist/taskforge_submission.zip").exists()


def test_editing_after_approval_makes_it_stale(proj):
    t = proj / "tasks/click-demo"
    rv.set_review(t, "approved", "Yamini")
    assert rv.status(t) == "approved"
    (t / "instruction.md").write_text("# changed after sign-off")
    assert rv.status(t) == "stale"
    assert run(proj, "export", "--out", str(proj / "dist")).exit_code == 1


def test_rejected_task_blocks_export_and_allow_flag_overrides(proj):
    t = proj / "tasks/click-demo"
    rv.set_review(t, "rejected", "Nikhil", "unclear spec")
    assert run(proj, "export", "--out", str(proj / "d1")).exit_code == 1
    assert run(proj, "export", "--out", str(proj / "d2"), "--allow-unreviewed").exit_code == 0


def test_review_list_and_card(proj):
    out = run(proj, "review", "--list").output
    assert "click-demo" in out and "pending" in out and "_golden" not in out
    assert "CHECKLIST" in rv.review_card(proj / "tasks/click-demo")


def test_generated_manifest_has_no_review_until_signed(proj):
    assert rv.status(proj / "tasks/click-demo") == "pending"
    with pytest.raises(FileNotFoundError):
        rv.set_review(proj / "tasks/_golden", "approved", "x")


def test_doctor_runs_and_reports(proj):
    r = run(proj, "doctor")
    assert "python >= 3.10" in r.output and r.exit_code in (0, 1)
