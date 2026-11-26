"""Step 8: the loop. baseline -> repo_intel -> propose -> novelty -> per task:
spec -> implement -> tests -> local nop/oracle -> critic -> package -> Harbor -> mutation.
A failed gate sends its error log back to the failing agent (max_retries), then the next-best candidate
for that archetype is tried; if none work the failure is logged to evidence/failures.md.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import llm
from .fsutil import write_lf
from .agents import critic, implementer, proposer, spec_writer, test_author
from .baseline import run_baseline
from .config import Config, load_archetypes
from .gitutil import apply_patch, pytest_ids, worktree
from .mutate import mutate, reward_from
from .novelty import best_per_archetype, filter_and_rank
from .packager import lint_instruction, package, sha256
from .repo_intel import load_or_build, summarize_for_prompt
from .validate import validate, write_validation_md

console = Console()


def slug(title: str, taken: set[str]) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    s = s if s.startswith("click-") else f"click-{s}"
    base, i = s, 2
    while s in taken:
        s, i = f"{base}-{i}", i + 1
    taken.add(s)
    return s


def prompt_hashes() -> dict[str, str]:
    return {name: llm.prompt_hash(mod.SYSTEM) for name, mod in
            {"proposer": proposer, "spec_writer": spec_writer, "implementer": implementer,
             "test_author": test_author, "critic": critic}.items()}


def _fail_text(res: dict, tail: str = "") -> str:
    return f"{res}\n{tail}"[-2500:]


def attempt_task(cfg: Config, run_dir: Path, repo: Path, summary: str, baseline: list[str], cand: dict,
                 task_id: str) -> dict:
    """Try to build ONE validated task from one candidate (max_retries tries). Returns a result dict."""
    ev = cfg.p(cfg.evidence_dir) / task_id
    ev.mkdir(parents=True, exist_ok=True)
    fb = {"spec": "", "impl": "", "tests": ""}
    log = ev / "attempts.jsonl"
    p2p = test_author.build_p2p(baseline)
    last = ""

    def note(n: int, stage: str, msg: str) -> None:
        nonlocal last
        last = f"[try {n}] {stage}: {msg}"
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"try": n, "stage": stage, "msg": msg[-2000:], "ts": time.time()}) + "\n")
        console.log(f"[yellow]{task_id} try {n} {stage} failed[/]: {msg[:200]}")

    def one_try(n: int) -> dict | None:
        """One full attempt. Returns the success dict, or None after recording a failed gate."""
        spec = spec_writer.write_spec(cfg, cand, summary, fb["spec"], tag=task_id)
        problems = lint_instruction(spec)
        if problems:
            fb["spec"] = "; ".join(problems)
            note(n, "spec-lint", fb["spec"])
            return None
        fb["spec"] = ""
        with worktree(repo, cfg.base_commit) as wt:
            patch, err = implementer.implement(cfg, wt, cand, spec, fb["impl"], tag=task_id)
        if err:
            fb["impl"] = err
            note(n, "implement", err)
            return None
        test_code = test_author.write_tests(cfg, spec, fb["tests"], tag=task_id)
        with worktree(repo, cfg.base_commit) as wt:  # gate: nop (no patch) -> every feature test must fail
            f2p, outcomes, out = test_author.feature_ids(wt, test_code)
        if not f2p:
            fb["tests"] = "no tests collected from your file:\n" + out[-1500:]
            note(n, "nop-collect", fb["tests"])
            return None
        passing = [t for t in f2p if outcomes.get(t) == "passed"]
        if passing:
            fb["tests"] = f"these tests PASS without the feature (too weak or feature exists): {passing}"
            note(n, "nop-local", fb["tests"])
            return None
        with worktree(repo, cfg.base_commit) as wt:  # gate: oracle (patch applied) -> everything passes
            ok, aerr = apply_patch(wt, patch)
            if not ok:
                fb["impl"] = f"patch does not apply cleanly: {aerr}"
                note(n, "oracle-apply", fb["impl"])
                return None
            write_lf(wt / test_author.TARGET, test_code)
            res, out = pytest_ids(wt, ["tests", "--continue-on-collection-errors"])
        if reward_from(res, f2p, p2p) < 1.0:
            failing = [t for t in f2p + p2p if res.get(t) != "passed"][:15]
            fb["impl"] = f"with your patch these tests fail: {failing}\n{out[-1500:]}"
            fb["tests"] = f"reference patch fails these tests (test may be wrong): {failing}\n{out[-800:]}"
            note(n, "oracle-local", fb["impl"])
            return None
        verdict = critic.review(cfg, spec, test_code, patch, tag=task_id)
        write_lf(ev / "critic.json", json.dumps(verdict, indent=1))
        if not verdict["approve"]:
            fb["spec"] = fb["tests"] = "critic issues: " + "; ".join(verdict["issues"])
            note(n, "critic", fb["spec"])
            return None
        fb["spec"] = fb["tests"] = ""
        task_dir = package(cfg, task_id, cand["archetype"], spec, patch, test_code, f2p, p2p)
        val: dict = {"task": task_id, "passed": True, "gates": {}, "skipped": "harbor disabled in config"}
        if cfg.harbor_enabled:
            val = validate(cfg, task_dir)
            if not val["passed"]:
                msg = _fail_text({k: v for k, v in val["gates"].items() if not v["pass"]}, val.get("error_log", ""))
                fb["impl"] = fb["tests"] = "harbor gate failed: " + msg
                note(n, "harbor", msg)
                return None
        mut = mutate(cfg, task_dir, repo, runner=cfg.mutation_runner)
        write_lf(ev / "mutation.json", json.dumps(mut, indent=1))
        write_validation_md(ev, val, mut)
        write_lf(ev / "validation.json", json.dumps(val, indent=1))
        if not mut["pass"]:
            surv = [m["desc"] for m in mut["mutants"] if m["status"] == "survived"]
            fb["tests"] = f"mutants survived (add tests AND state the behaviour in the spec): {surv}"
            fb["spec"] = "state every boundary/behaviour precisely: " + "; ".join(surv)
            note(n, "mutation", f"kill rate {mut['kill_rate']:.0%}; survived={surv}")
            return None
        manifest = {
            "task_id": task_id, "archetype": cand["archetype"], "title": cand["title"],
            "base_commit": cfg.base_commit, "release_tag": cfg.tag,
            "models": {"main": cfg.models.main.model_dump(), "critic": cfg.models.critic.model_dump()},
            "prompt_hashes": prompt_hashes(), "patch_sha256": sha256(patch),
            "instruction_sha256": sha256(spec), "tests_sha256": sha256(test_code),
            "gates": val.get("gates", {}), "harbor_skipped": not cfg.harbor_enabled,
            "mutation": {k: mut[k] for k in ("runner", "kill_rate", "killed", "valid")},
            "f2p_count": len(f2p), "p2p_count": len(p2p), "retries": n - 1,
            "critic": verdict, "review": None, "run_id": run_dir.name, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        write_lf(task_dir / "manifest.json", json.dumps(manifest, indent=1))
        return {"ok": True, "task_id": task_id, "manifest": manifest}

    for n in range(1, cfg.max_retries + 1):
        try:
            r = one_try(n)
        except Exception as ex:  # LLMError, bad JSON, git/pytest hiccups: a failed try, never a crashed run
            note(n, "error", f"{type(ex).__name__}: {ex}")
            continue
        if r:
            return r
    return {"ok": False, "task_id": task_id, "reason": last}


def build_one(cfg, run_dir, repo, summary, baseline, cands: list[dict], taken: set[str]) -> dict:
    tries = []
    for cand in cands:  # best first, then spares
        task_id = slug(cand["title"], taken)
        r = attempt_task(cfg, run_dir, repo, summary, baseline, cand, task_id)
        if r["ok"]:
            r["fallbacks_used"] = len(tries)
            return r
        tries.append({"candidate": cand["title"], "reason": r["reason"]})
    return {"ok": False, "archetype": cands[0]["archetype"], "failures": tries}


def run_pipeline(cfg: Config, n_tasks: int | None = None, archetype_ids: list[str] | None = None,
                 dry_run: bool = False, use_docker: bool = True, baseline_from: Path | None = None,
                 check_upstream: bool = True) -> dict:
    n_tasks = n_tasks or cfg.n_tasks
    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = cfg.p("runs") / run_id
    llm.set_run_dir(run_dir)
    warn = llm.check_family(cfg)
    if warn:
        console.print(f"[bold yellow]WARNING:[/] {warn}")
    # 1-2. pin + baseline
    if baseline_from:
        (run_dir).mkdir(parents=True, exist_ok=True)
        baseline = json.loads((baseline_from / "baseline_tests.json").read_text(encoding="utf-8"))
        from .baseline import clone_and_pin
        clone_and_pin(cfg)
    else:
        console.print("[cyan]baseline:[/] pin commit, build, run tests...")
        console.print(run_baseline(cfg, run_dir, use_docker=use_docker))
        baseline = json.loads((run_dir / "baseline_tests.json").read_text(encoding="utf-8"))
    repo = cfg.p(cfg.work_dir)
    # 3. repo intelligence
    rmap = load_or_build(repo, cfg.base_commit, cfg.p("work/cache"), package_dir=cfg.package_dir)
    write_lf(run_dir / "repo_map.json", json.dumps(rmap, indent=1))
    summary = summarize_for_prompt(rmap)
    # 4-5. propose + novelty
    arch = load_archetypes(cfg.p("archetypes.yaml"))
    chosen = [a for a in arch["archetypes"] if not archetype_ids or a["id"] in archetype_ids][:n_tasks]
    cands: list[dict] = []
    for a in chosen:
        a = {**a, "rules": arch["common_rules"] + a["rules"]}
        try:
            cands += proposer.propose(cfg, a, summary, [c["title"] for c in cands], tag="propose")
        except Exception as ex:
            console.print(f"[red]proposer failed for {a['id']}:[/] {type(ex).__name__}: {ex}")
    kept, rejected = filter_and_rank(cands, repo, rmap, check_upstream=check_upstream,
                                     semantic_cfg=cfg if cfg.semantic_novelty else None)
    write_lf(run_dir / "candidates.json", json.dumps({"kept": kept, "rejected": rejected}, indent=1))
    picks = best_per_archetype(kept)
    console.print(f"proposed {len(cands)}, kept {len(kept)}, rejected {len(rejected)}")
    for aid, lst in picks.items():
        console.print(f"  [green]{aid}[/]: {lst[0]['title']}  (+{len(lst) - 1} spare)")
    if dry_run:
        return {"run_id": run_id, "picks": {k: [c["title"] for c in v] for k, v in picks.items()}}
    # 6-8. build tasks (at most cfg.parallel_tasks at once)
    taken: set[str] = {p.name for p in cfg.p(cfg.tasks_dir).glob("*") if p.is_dir()}
    results = []
    with ThreadPoolExecutor(max_workers=max(1, cfg.parallel_tasks)) as ex:
        futs = [ex.submit(build_one, cfg, run_dir, repo, summary, baseline, lst, taken) for lst in picks.values()]
        results = [f.result() for f in futs]
    _write_summary(cfg, run_id, results)
    return {"run_id": run_id, "results": results}


def _write_summary(cfg: Config, run_id: str, results: list[dict]) -> None:
    ev = cfg.p(cfg.evidence_dir)
    ev.mkdir(parents=True, exist_ok=True)
    t = Table(title=f"TaskForge run {run_id} - click @ {cfg.tag}")
    for c in ("Task", "Archetype", "nop", "oracle", "Mutants killed", "Retries", "Status"):
        t.add_column(c)
    rows = ["| Task | Archetype | nop | oracle | Mutants killed | Retries | Status |", "|---|---|---|---|---|---|---|"]
    fails = []
    for r in results:
        if r["ok"]:
            m = r["manifest"]
            g = m["gates"]
            nop = g.get("nop_is_0", {}).get("reward", "n/a (harbor off)")
            orc = g.get("oracle_is_1", {}).get("reward", "n/a (harbor off)")
            row = [r["task_id"], m["archetype"], str(nop), str(orc), f"{m['mutation']['kill_rate']:.0%}",
                   str(m["retries"]), "READY"]
        else:
            row = ["-", r.get("archetype", "?"), "-", "-", "-", "-", "DROPPED"]
            fails.append(r)
        t.add_row(*row)
        rows.append("| " + " | ".join(row) + " |")
    console.print(t)
    write_lf(ev / "summary.md", f"# Run {run_id}\n\n" + "\n".join(rows) + "\n")
    with open(ev / "failures.md", "a", encoding="utf-8") as f:
        for r in fails:
            f.write(f"\n## Run {run_id}: archetype {r['archetype']} dropped\n")
            for x in r["failures"]:
                f.write(f"- {x['candidate']}: {x['reason'][:600]}\n")
    fx = ev / "fixes.md"
    if not fx.exists():
        write_lf(fx, "# Manual fixes log\n\nNo manual fixes.\n")
