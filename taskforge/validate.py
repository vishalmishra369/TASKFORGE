"""Step 7: validation gates. nop == 0.0, oracle == 1.0, oracle x3 identical, null reward = crash.

Harbor flags follow the build guide (`harbor run -p <task> -a nop|oracle -k 1 -o <dir> --no-delete -y`).
Run `harbor run --help` once and adjust `harbor_flags` in config.yaml if your version differs.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .config import Config

DEFAULT_FLAGS = ["-k", "{k}", "--no-delete", "-y"]


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def find_reward(out_dir: Path) -> float | None:
    """Find the reward in a Harbor job folder (layouts verified against harbor 0.25.0 source):
    1. <trial>/verifier/reward.txt          (a float)
    2. <trial>/verifier/reward.json         (flat {"reward": x, ...}; single key is accepted too)
    3. <trial>/result.json -> verifier_result.rewards.reward   (what Harbor itself reports)
    None = no verifier output at all = environment crash.
    """
    for f in sorted(out_dir.rglob("reward.txt")):
        try:
            return float(f.read_text().strip())
        except ValueError:
            continue
    for f in sorted(out_dir.rglob("reward.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(d, dict):
            if _num(d.get("reward")) is not None:
                return _num(d["reward"])
            vals = [_num(v) for v in d.values() if _num(v) is not None]
            if len(vals) == 1:
                return vals[0]
    for f in sorted(out_dir.rglob("result.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        rewards = ((d.get("verifier_result") or {}).get("rewards")) if isinstance(d, dict) else None
        if isinstance(rewards, dict):
            if _num(rewards.get("reward")) is not None:
                return _num(rewards["reward"])
            vals = [_num(v) for v in rewards.values() if _num(v) is not None]
            if len(vals) == 1:
                return vals[0]
    return None


def tree_text(path: Path, max_lines: int = 200) -> str:
    lines = [str(p.relative_to(path)) for p in sorted(path.rglob("*"))][:max_lines]
    return "\n".join(lines)


def harbor(task_dir: Path, agent: str, out_dir: Path, k: int, timeout: int = 3600,
           flags: list[str] | None = None) -> tuple[float | None, str]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    flags = [f.format(k=k) for f in (flags or DEFAULT_FLAGS)]
    cmd = ["harbor", "run", "-p", str(task_dir), "-a", agent, *flags, "-o", str(out_dir)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log = f"$ {' '.join(cmd)}\n{p.stdout[-4000:]}\n{p.stderr[-4000:]}"
    except FileNotFoundError:
        return None, "harbor CLI not found: pip install 'harbor==0.25.*'"
    except subprocess.TimeoutExpired:
        return None, "harbor timed out"
    (out_dir / "harbor_tree.txt").write_text(tree_text(out_dir))
    (out_dir / "harbor_console.log").write_text(log)
    return find_reward(out_dir), log


def validate(cfg: Config, task_dir: Path, evidence_root: Path | None = None, flake_runs: int = 3) -> dict:
    """Run all Harbor gates for one task. Returns the validation dict (also written to disk)."""
    tid = task_dir.name
    ev = (evidence_root or cfg.p(cfg.evidence_dir)) / tid
    ev.mkdir(parents=True, exist_ok=True)
    res: dict = {"task": tid, "gates": {}}
    nop, nop_log = harbor(task_dir, "nop", ev / "nop", cfg.harbor_k, flags=cfg.harbor_flags)
    res["gates"]["nop_is_0"] = {"reward": nop, "pass": nop == 0.0}
    oracle, o_log = harbor(task_dir, "oracle", ev / "oracle", cfg.harbor_k, flags=cfg.harbor_flags)
    res["gates"]["oracle_is_1"] = {"reward": oracle, "pass": oracle == 1.0}
    if nop is None or oracle is None:
        res["gates"]["no_crash"] = {"pass": False, "note": "null reward = environment crash"}
        res["error_log"] = (nop_log if nop is None else o_log)[-3000:]
    else:
        res["gates"]["no_crash"] = {"pass": True}
    if oracle == 1.0:
        rewards = [oracle]
        for i in range(2, flake_runs + 1):
            r, _ = harbor(task_dir, "oracle", ev / f"oracle_run{i}", cfg.harbor_k, flags=cfg.harbor_flags)
            rewards.append(r)
        res["gates"]["oracle_stable"] = {"rewards": rewards, "pass": len(set(rewards)) == 1 and rewards[0] == 1.0}
    else:
        res["gates"]["oracle_stable"] = {"rewards": [], "pass": False, "note": "skipped: oracle != 1.0"}
    if not res["gates"]["oracle_is_1"]["pass"] or not res["gates"]["nop_is_0"]["pass"]:
        res.setdefault("error_log", (o_log if nop == 0.0 else nop_log)[-3000:])
    res["passed"] = all(g["pass"] for g in res["gates"].values())
    (ev / "validation.json").write_text(json.dumps(res, indent=1))
    return res


def write_validation_md(ev_dir: Path, res: dict, mutation: dict | None) -> None:
    lines = [f"# Validation: {res.get('task')}", "", "| Gate | Result | Detail |", "|---|---|---|"]
    for name, g in res.get("gates", {}).items():
        detail = {k: v for k, v in g.items() if k != "pass"}
        lines.append(f"| {name} | {'PASS' if g['pass'] else 'FAIL'} | {detail} |")
    if mutation:
        lines += ["", f"Mutation kill rate: {mutation['kill_rate']:.0%} "
                      f"({mutation['killed']}/{mutation['valid']} valid mutants killed)",
                  "", "| # | Mutation | Killed |", "|---|---|---|"]
        for i, m in enumerate(mutation["mutants"], 1):
            lines.append(f"| {i} | {m['desc']} | {m['status']} |")
    (ev_dir / "validation.md").write_text("\n".join(lines) + "\n")
