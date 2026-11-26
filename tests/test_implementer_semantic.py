import json
import subprocess
from pathlib import Path

import pytest

from taskforge import llm
from taskforge.agents import implementer
from taskforge.config import load_config
from taskforge.novelty import filter_and_rank
from taskforge.repo_intel import build_repo_map


def _git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "src/click").mkdir(parents=True)
    (tmp_path / "src/click/types.py").write_text("x = 1\n")
    (tmp_path / "src/click/__init__.py").write_text("")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "-c", "user.email=a@b", "-c", "user.name=n", "add", ".")
    _git(tmp_path, "-c", "user.email=a@b", "-c", "user.name=n", "commit", "-qm", "base")
    return tmp_path


def mock_cfg():
    cfg = load_config("config.yaml")
    cfg.models.main.provider = cfg.models.critic.provider = "mock"
    return cfg


CAND = {"files_touched": ["src/click/types.py"]}


def test_edit_mode_works(repo):
    llm.set_mock_responses({"implementer": json.dumps(
        {"edits": [{"path": "src/click/types.py", "search": "x = 1\n", "replace": "x = 1\ny = 2\n"}]})})
    patch, err = implementer.implement(mock_cfg(), repo, CAND, "spec")
    assert err is None and "+y = 2" in patch


def test_whole_file_fallback_when_search_does_not_match(repo):
    llm.set_mock_responses({
        "implementer": json.dumps({"edits": [{"path": "src/click/types.py", "search": "NOPE", "replace": "z"}]}),
        "implementer_whole": json.dumps({"files": [{"path": "src/click/types.py", "content": "x = 1\ny = 2\n"}]}),
    })
    patch, err = implementer.implement(mock_cfg(), repo, CAND, "spec")
    assert err is None and "+y = 2" in patch


def test_both_modes_fail_gives_clear_error_and_clean_worktree(repo):
    llm.set_mock_responses({"implementer": "not json at all",
                            "implementer_whole": json.dumps({"files": [{"path": "tests/x.py", "content": "1"}]})})
    patch, err = implementer.implement(mock_cfg(), repo, CAND, "spec")
    assert patch is None and "fallback also failed" in err
    assert (repo / "src/click/types.py").read_text() == "x = 1\n"


def test_huge_patch_is_rejected(repo):
    big = "x = 1\n" + "".join(f"v{i} = {i}\n" for i in range(600))
    llm.set_mock_responses({"implementer": json.dumps(
        {"edits": [{"path": "src/click/types.py", "search": "x = 1\n", "replace": big}]})})
    patch, err = implementer.implement(mock_cfg(), repo, CAND, "spec")
    assert patch is None and "limit" in err


def test_never_edits_tests_dir(repo):
    llm.set_mock_responses({"implementer": json.dumps(
        {"edits": [], "new_files": [{"path": "tests/test_a.py", "content": "1"}]}),
        "implementer_whole": json.dumps({"files": []})})
    patch, err = implementer.implement(mock_cfg(), repo, CAND, "spec")
    assert patch is None and not (repo / "tests").exists()


def _cand():
    return {"archetype": "a", "title": "Fancy thing", "api_sketch": "make_fancy", "behaviours": ["a", "b", "c"],
            "edge_cases": ["x", "y"], "est_lines": 100, "new_names": ["MakeFancyThing"]}


def test_semantic_check_rejects_when_llm_says_it_exists(repo):
    cfg = mock_cfg()
    rm = build_repo_map(repo)
    llm.set_mock_responses({"novelty_semantic": json.dumps({"exists": True, "evidence": "click has it as Fancy"})})
    kept, rej = filter_and_rank([_cand()], repo, rm, check_upstream=False, semantic_cfg=cfg)
    assert not kept and "semantic" in rej[0]["rejected_reasons"][0]


def test_semantic_check_keeps_when_llm_says_new(repo):
    llm.set_mock_responses({"novelty_semantic": json.dumps({"exists": False, "evidence": ""})})
    kept, rej = filter_and_rank([_cand()], repo, build_repo_map(repo), check_upstream=False, semantic_cfg=mock_cfg())
    assert len(kept) == 1 and not rej


def test_semantic_check_fails_open_and_notes_it(repo):
    llm.set_mock_responses({})  # model call raises
    kept, rej = filter_and_rank([_cand()], repo, build_repo_map(repo), check_upstream=False, semantic_cfg=mock_cfg())
    assert len(kept) == 1 and any("unavailable" in n for n in kept[0]["notes"])
