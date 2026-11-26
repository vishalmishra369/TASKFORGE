import json

import pytest

from taskforge import validate as V
from taskforge.config import load_config


def _w(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_find_reward_reward_txt(tmp_path):
    _w(tmp_path / "job/trial/verifier/reward.txt", "1.0")
    assert V.find_reward(tmp_path) == 1.0


def test_find_reward_reward_json_flat_and_single_key(tmp_path):
    _w(tmp_path / "a/verifier/reward.json", json.dumps({"reward": 0.5, "other": 3}))
    assert V.find_reward(tmp_path / "a") == 0.5
    _w(tmp_path / "b/verifier/reward.json", json.dumps({"score": 0.0}))
    assert V.find_reward(tmp_path / "b") == 0.0


def test_find_reward_from_result_json(tmp_path):
    _w(tmp_path / "t/result.json", json.dumps({"verifier_result": {"rewards": {"reward": 1.0}}}))
    assert V.find_reward(tmp_path) == 1.0


def test_find_reward_none_means_crash(tmp_path):
    _w(tmp_path / "t/result.json", json.dumps({"verifier_result": None}))
    _w(tmp_path / "t/verifier/test-stdout.txt", "boom")
    assert V.find_reward(tmp_path) is None


def test_harbor_missing_cli(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(V.subprocess, "run", boom)
    reward, log = V.harbor(tmp_path, "nop", tmp_path / "o", 1)
    assert reward is None and "harbor CLI not found" in log


def _gates(monkeypatch, tmp_path, rewards):
    """rewards: dict agent -> list of rewards returned call after call."""
    calls = {k: list(v) for k, v in rewards.items()}

    def fake(task_dir, agent, out_dir, k, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        return calls[agent].pop(0), "log"

    monkeypatch.setattr(V, "harbor", fake)
    cfg = load_config("config.yaml")
    task = tmp_path / "t1"
    task.mkdir()
    return V.validate(cfg, task, evidence_root=tmp_path / "ev")


def test_validate_all_gates_pass(monkeypatch, tmp_path):
    res = _gates(monkeypatch, tmp_path, {"nop": [0.0], "oracle": [1.0, 1.0, 1.0]})
    assert res["passed"] and (tmp_path / "ev/t1/validation.json").exists()


def test_validate_flaky_oracle_fails(monkeypatch, tmp_path):
    res = _gates(monkeypatch, tmp_path, {"nop": [0.0], "oracle": [1.0, 1.0, 0.5]})
    assert not res["passed"] and not res["gates"]["oracle_stable"]["pass"]


@pytest.mark.parametrize("nop,oracle,failing", [(0.5, [1.0] * 3, "nop_is_0"), (0.0, [0.8], "oracle_is_1")])
def test_validate_wrong_rewards_fail(monkeypatch, tmp_path, nop, oracle, failing):
    res = _gates(monkeypatch, tmp_path, {"nop": [nop], "oracle": oracle})
    assert not res["passed"] and not res["gates"][failing]["pass"]


def test_validate_null_reward_is_crash(monkeypatch, tmp_path):
    res = _gates(monkeypatch, tmp_path, {"nop": [None], "oracle": [1.0, 1.0, 1.0]})
    assert not res["passed"] and not res["gates"]["no_crash"]["pass"]
