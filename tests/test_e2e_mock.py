"""Offline end-to-end: real click clone + mock LLM replaying the golden answers; Harbor is skipped.
Run with:  TASKFORGE_E2E=1 pytest tests/test_e2e_mock.py   (needs work/click and runs/baseline from `taskforge baseline --no-docker`)
"""
import json
import os
import shutil
from pathlib import Path

import pytest

from taskforge import llm
from taskforge.config import load_config
from taskforge.orchestrator import run_pipeline

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(os.environ.get("TASKFORGE_E2E") != "1" or not (ROOT / "work/click/.git").exists()
                                or not (ROOT / "runs/baseline/baseline_tests.json").exists(),
                                reason="set TASKFORGE_E2E=1 and run the baseline first")


def test_pipeline_end_to_end_with_mock(tmp_path):
    cfg = load_config(ROOT / "config.yaml")
    cfg.root = tmp_path
    shutil.copy(ROOT / "archetypes.yaml", tmp_path / "archetypes.yaml")
    cfg.work_dir = str(ROOT / "work/click")
    cfg.tasks_dir, cfg.evidence_dir = str(tmp_path / "tasks"), str(tmp_path / "evidence")
    (tmp_path / "tasks").mkdir()
    cfg.harbor_enabled = False
    cfg.models.main.provider = cfg.models.critic.provider = "mock"
    cfg.models.critic.model = "mock-critic"
    llm.set_mock_responses(json.loads((Path(__file__).parent / "fixtures/golden_responses.json").read_text()))
    out = run_pipeline(cfg, 1, ["new_param_type"], baseline_from=ROOT / "runs/baseline", check_upstream=False)
    r = out["results"][0]
    assert r["ok"], r
    td = tmp_path / "tasks" / r["task_id"]
    m = json.loads((td / "manifest.json").read_text())
    assert m["mutation"]["kill_rate"] >= 0.8 and m["retries"] == 0 and len(m["base_commit"]) == 40
    assert (tmp_path / "evidence" / "summary.md").exists()
