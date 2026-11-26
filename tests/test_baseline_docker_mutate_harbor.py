import json
from pathlib import Path

from taskforge import baseline as B
from taskforge import mutate as M
from taskforge.config import load_config


def test_dockerfile_pins_commit_and_hides_upstream_history():
    cfg = load_config("config.yaml")
    d = B.render_dockerfile(cfg)
    assert f"git checkout {cfg.base_commit}" in d
    for needle in ("git remote remove origin", "update-ref -d", "gc --prune=now"):
        assert needle in d
    assert "less" in d  # pager tests need it


def test_baseline_keeps_only_tests_that_pass_every_run(monkeypatch, tmp_path):
    cfg = load_config("config.yaml")
    runs = iter([
        {"t::a": "passed", "t::b": "passed", "t::c": "failed", "t::d": "passed"},
        {"t::a": "passed", "t::b": "failed", "t::c": "failed", "t::d": "passed"},
        {"t::a": "passed", "t::b": "passed", "t::c": "failed", "t::d": "skipped"},
    ])
    monkeypatch.setattr(B, "clone_and_pin", lambda c: tmp_path)
    monkeypatch.setattr(B, "_pytest_local", lambda wd, out: next(runs))
    monkeypatch.setattr(B, "preflight_local", lambda wd: None)
    summary = B.run_baseline(cfg, tmp_path / "run", use_docker=False)
    assert json.loads((tmp_path / "run/baseline_tests.json").read_text()) == ["t::a"]
    excl = json.loads((tmp_path / "run/baseline_excluded.json").read_text())
    assert set(excl) == {"t::b", "t::c", "t::d"} and summary["stable_passing"] == 1


def test_mutation_harbor_runner_counts_kills(monkeypatch, tmp_path):
    cfg = load_config("config.yaml")
    golden = Path("tasks/_golden")
    seq = iter([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0])  # 8 killed, 2 survived

    def fake(task_dir, agent, out_dir, k, **kw):
        assert agent == "oracle" and (task_dir / "solution/solution.patch").exists()
        return next(seq), ""

    monkeypatch.setattr(M, "harbor", fake)
    res = M.mutate(cfg, golden, tmp_path, runner="harbor")
    assert res["runner"] == "harbor" and res["valid"] == 10 and res["killed"] == 8 and res["pass"]


def test_mutation_harbor_crash_is_invalid_not_killed(monkeypatch, tmp_path):
    cfg = load_config("config.yaml")
    monkeypatch.setattr(M, "harbor", lambda *a, **k: (None, "crash"))
    res = M.mutate(cfg, Path("tasks/_golden"), tmp_path, runner="harbor")
    assert res["valid"] == 0 and res["killed"] == 0 and not res["pass"]


def test_baseline_never_writes_empty_list(monkeypatch, tmp_path):
    import pytest
    cfg = load_config("config.yaml")
    monkeypatch.setattr(B, "clone_and_pin", lambda c: tmp_path)
    monkeypatch.setattr(B, "_pytest_local", lambda wd, out: {})
    monkeypatch.setattr(B, "preflight_local", lambda wd: None)
    with pytest.raises(RuntimeError, match="nothing was written"):
        B.run_baseline(cfg, tmp_path / "run", use_docker=False)
    assert not (tmp_path / "run/baseline_tests.json").exists()


def test_local_preflight_gives_actionable_message(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setattr(B, "run", lambda *a, **k: type("P", (), {"returncode": 1})())
    with pytest.raises(RuntimeError, match="pip install -e"):
        B.preflight_local(tmp_path)
