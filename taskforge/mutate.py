"""Mutation testing of solution.patch: break the reference solution on purpose; the tests must notice.

A mutant edits ONE added line of the patch (line counts stay the same, so the patch still applies).
Runners:
  local  - git worktree at base_commit + mutant + feature tests + whole suite (seconds, default)
  harbor - copy of the task with the mutant as solution.patch, run `oracle` (slow, official)
killed = reward < 1.0. Mutants that do not apply or do not compile are 'invalid' and not counted.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import tempfile
from pathlib import Path

from .config import Config
from .gitutil import apply_patch, pytest_ids, run, worktree
from .validate import harbor

OPS: list[tuple[str, str, str]] = [  # (description, regex, replacement)
    ("flip == to !=", r"==", "!="),
    ("flip != to ==", r"!=", "=="),
    ("boundary < to <=", r"(?<![<=!>])<(?![<=])", "<="),
    ("boundary <= to <", r"<=", "<"),
    ("boundary > to >=", r"(?<![<=!>-])>(?![>=])", ">="),
    ("boundary >= to >", r">=", ">"),
    ("flip and to or", r"\band\b", "or"),
    ("flip or to and", r"\bor\b", "and"),
    ("flip True to False", r"\bTrue\b", "False"),
    ("flip False to True", r"\bFalse\b", "True"),
    ("drop 'not'", r"\bnot\s+", ""),
]


def _added_lines(patch: str):
    """Yield (patch_line_index, file, text) for added CODE lines in python files under src/.

    Docstring lines are skipped (mutating prose can never be 'killed' and would deflate the score).
    Docstring state is tracked per hunk by counting triple quotes on context and added lines.
    """
    cur = None
    in_doc = False
    for i, line in enumerate(patch.splitlines()):
        if line.startswith("+++ "):
            cur = line[4:].removeprefix("b/")
            in_doc = False
            continue
        if line.startswith("@@"):
            in_doc = False
            continue
        if line.startswith("-") or line.startswith("---") or not line:
            continue
        text = line[1:]
        quotes = text.count('"""') + text.count("'''")
        was_doc = in_doc
        if quotes % 2 == 1:
            in_doc = not in_doc
        if line.startswith("+") and cur and cur.endswith(".py") and cur.startswith("src/") \
                and not was_doc and quotes == 0 and not in_doc:
            yield i, cur, text


def _is_code(text: str) -> bool:
    s = text.strip()
    return bool(s) and not s.startswith(("#", '"""', "'''", '"', "'", "@", "import ", "from "))


def generate_mutants(patch: str, limit: int = 10) -> list[dict]:
    lines = patch.splitlines()
    cands: list[dict] = []
    for i, f, text in _added_lines(patch):
        if not _is_code(text):
            continue
        for desc, rx, rep in OPS:
            m = re.search(rx, text)
            if m:
                cands.append({"idx": i, "file": f, "desc": f"{desc}: `{text.strip()[:60]}`",
                              "new": text[: m.start()] + rep + text[m.end():]})
        mi = re.search(r"\b(\d+)\b", text)
        if mi and "fail(" not in text and not re.search(r"['\"].*\d.*['\"]", text):
            n = int(mi.group(1))
            cands.append({"idx": i, "file": f, "desc": f"change constant {n}->{n + 1}: `{text.strip()[:60]}`",
                          "new": text[: mi.start()] + str(n + 1) + text[mi.end():]})
        if text.strip().startswith("return ") and text.strip() != "return None":
            ind = text[: len(text) - len(text.lstrip())]
            cands.append({"idx": i, "file": f, "desc": f"return None early: `{text.strip()[:60]}`",
                          "new": f"{ind}return None"})
        if re.search(r"(fail\(|raise |BadParameter\(|UsageError\()", text):
            ms = re.search(r"(f?)(['\"])(.+?)\2", text)
            if ms:
                new = text[: ms.end(3)] + " (mutated)" + text[ms.end(3):]
                cands.append({"idx": i, "file": f, "desc": f"change error message: `{text.strip()[:60]}`",
                              "new": new})
    rnd = random.Random(int(hashlib.sha256(patch.encode()).hexdigest()[:8], 16))
    rnd.shuffle(cands)
    chosen, used = [], set()
    for c in cands:  # prefer one mutation per line first
        if c["idx"] not in used:
            used.add(c["idx"])
            chosen.append(c)
    for c in cands:
        if len(chosen) >= limit:
            break
        if c not in chosen:
            chosen.append(c)
    out = []
    for c in chosen[:limit]:
        new_lines = list(lines)
        new_lines[c["idx"]] = "+" + c["new"]
        out.append({"desc": c["desc"], "file": c["file"], "patch": "\n".join(new_lines) + "\n"})
    return out


def reward_from(outcomes: dict[str, str], f2p: list[str], p2p: list[str]) -> float:
    if not all(outcomes.get(t) == "passed" for t in p2p):
        return 0.0
    return sum(outcomes.get(t) == "passed" for t in f2p) / len(f2p) if f2p else 0.0


def _local_reward(repo: Path, base_commit: str, patch: str, test_code: str, f2p: list[str],
                  p2p: list[str]) -> tuple[float | None, str]:
    with worktree(repo, base_commit) as wt:
        ok, err = apply_patch(wt, patch)
        if not ok:
            return None, f"patch does not apply: {err}"
        for f in {m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+\.py)$", patch, re.M)}:
            r = run(["python", "-m", "py_compile", f], cwd=wt)
            if r.returncode != 0:
                return None, f"does not compile: {f}"
        (wt / "tests/test_taskforge_feature.py").write_text(test_code)
        res, _ = pytest_ids(wt, ["tests", "--continue-on-collection-errors"])
        return reward_from(res, f2p, p2p), ""


def mutate(cfg: Config, task_dir: Path, repo: Path, limit: int = 10, runner: str | None = None) -> dict:
    runner = runner or cfg.mutation_runner
    patch = (task_dir / "solution/solution.patch").read_text()
    test_code = (task_dir / "tests/test_feature.py").read_text()
    f2p = json.loads((task_dir / "tests/fail_to_pass.json").read_text())
    p2p = json.loads((task_dir / "tests/pass_to_pass.json").read_text())
    results = []
    for m in generate_mutants(patch, limit):
        if runner == "harbor":
            tmp = Path(tempfile.mkdtemp(prefix="tf_mut_"))
            td = tmp / task_dir.name
            shutil.copytree(task_dir, td)
            (td / "solution/solution.patch").write_text(m["patch"])
            reward, _ = harbor(td, "oracle", tmp / "out", cfg.harbor_k, flags=cfg.harbor_flags)
            shutil.rmtree(tmp, ignore_errors=True)
            err = "" if reward is not None else "harbor crash"
        else:
            reward, err = _local_reward(repo, cfg.base_commit, m["patch"], test_code, f2p, p2p)
        status = "invalid" if reward is None else ("killed" if reward < 1.0 else "survived")
        results.append({"desc": m["desc"], "status": status, "reward": reward, "note": err})
    valid = [r for r in results if r["status"] != "invalid"]
    killed = sum(r["status"] == "killed" for r in valid)
    rate = killed / len(valid) if valid else 0.0
    return {"runner": runner, "kill_rate": rate, "killed": killed, "valid": len(valid),
            "total": len(results), "mutants": results,
            "pass": bool(valid) and rate >= cfg.mutation_min_kill_rate}
