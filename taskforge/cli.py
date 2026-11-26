"""TaskForge CLI. `taskforge --help` lists: init, generate, validate, export, run (+ baseline, llm-check)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from . import llm
from .fsutil import write_lf
from .baseline import clone_and_pin, run_baseline
from .config import load_config
from . import review as rv
from .orchestrator import run_pipeline
from .validate import validate as validate_task, write_validation_md

app = typer.Typer(no_args_is_help=True, help="TaskForge: self-checking factory for Harbor coding tasks.")
console = Console()
CONFIG = typer.Option("config.yaml", "--config", "-c", help="Path to config.yaml")


@app.command()
def init(config: str = CONFIG, baseline: bool = typer.Option(True, help="Also run the baseline tests"),
         docker: bool = typer.Option(True, help="Run baseline inside Docker (false = local venv)")):
    """Clone the repo, check out base_commit, verify the 40-char hash, run the baseline."""
    cfg = load_config(config)
    clone_and_pin(cfg)
    console.print(f"[green]OK[/] base_commit {cfg.base_commit} (tag {cfg.tag})")
    if baseline:
        run_dir = cfg.p("runs") / "baseline"
        console.print(run_baseline(cfg, run_dir, use_docker=docker))
        console.print(f"results in {run_dir}")


@app.command()
def baseline(config: str = CONFIG, docker: bool = typer.Option(True)):
    """Run only the baseline (3x pytest) and write baseline_tests.json."""
    cfg = load_config(config)
    console.print(run_baseline(cfg, cfg.p("runs") / "baseline", use_docker=docker))


@app.command()
def generate(config: str = CONFIG, tasks: int = typer.Option(5, "--tasks", "-n"),
             dry_run: bool = typer.Option(False, "--dry-run", help="Only propose + filter, print the picks"),
             archetype: Optional[list[str]] = typer.Option(None, "--archetype", "-a"),
             docker: bool = typer.Option(True), no_upstream: bool = typer.Option(False, "--no-upstream-check")):
    """Propose -> novelty filter -> (unless --dry-run) generate and validate task packages."""
    cfg = load_config(config)
    base = cfg.p("runs") / "baseline"
    out = run_pipeline(cfg, tasks, archetype, dry_run=dry_run, use_docker=docker,
                       baseline_from=base if (base / "baseline_tests.json").exists() else None,
                       check_upstream=not no_upstream)
    console.print(f"run {out['run_id']} done")


@app.command()
def validate(task: Optional[Path] = typer.Argument(None, help="tasks/<id>"), all: bool = typer.Option(False, "--all"),
             mutation: bool = typer.Option(False, "--mutation"), config: str = CONFIG):
    """Run the Harbor gates (nop, oracle, x3 flake) for one task or all; --mutation adds mutants."""
    from .mutate import mutate
    cfg = load_config(config)
    dirs = sorted(p for p in cfg.p(cfg.tasks_dir).iterdir() if p.is_dir()) if all else [task]
    if not dirs or dirs[0] is None:
        raise typer.BadParameter("give a task dir or --all")
    bad = 0
    for d in dirs:
        res = validate_task(cfg, d)
        mut = None
        if mutation:
            mut = mutate(cfg, d, cfg.p(cfg.work_dir))
            write_lf(cfg.p(cfg.evidence_dir) / d.name / "mutation.json", json.dumps(mut, indent=1))
            res["passed"] = res["passed"] and mut["pass"]
        write_validation_md(cfg.p(cfg.evidence_dir) / d.name, res, mut)
        console.print(f"{d.name}: {'[green]PASS[/]' if res['passed'] else '[red]FAIL[/]'}")
        bad += not res["passed"]
    raise typer.Exit(code=1 if bad else 0)


@app.command()
def review(task: Optional[Path] = typer.Argument(None, help="tasks/<id>; omit with --list"),
           list_: bool = typer.Option(False, "--list", help="Show review status of every task"),
           approve: bool = typer.Option(False, "--approve"), reject: bool = typer.Option(False, "--reject"),
           by: str = typer.Option("", "--by", help="Reviewer name (required to approve/reject)"),
           note: str = typer.Option("", "--note"), config: str = CONFIG):
    """Human sign-off. `review tasks/<id>` shows the card and asks; or use --approve/--reject --by NAME."""
    cfg = load_config(config)
    tdir = cfg.p(cfg.tasks_dir)
    if list_ or task is None:
        for d in sorted(p for p in tdir.iterdir() if p.is_dir() and not p.name.startswith("_")):
            console.print(f"{d.name:40s} {rv.status(d)}")
        return
    console.print(rv.review_card(task))
    if not (approve or reject):
        if not typer.confirm("Approve this task?", default=False):
            if not typer.confirm("Mark it rejected?", default=False):
                return
            reject = True
        else:
            approve = True
    if approve and reject:
        raise typer.BadParameter("choose --approve or --reject, not both")
    who = by or typer.prompt("Reviewer name")
    rv.set_review(task, "approved" if approve else "rejected", who, note)
    console.print(f"[green]{task.name}: {'approved' if approve else 'rejected'} by {who}[/]")


@app.command()
def export(out: Path = typer.Option(Path("dist"), "--out"), config: str = CONFIG,
           allow_unreviewed: bool = typer.Option(False, "--allow-unreviewed",
                                                 help="Skip the human sign-off check (not for submission)")):
    """Copy approved tasks/ (without _golden) + evidence/ into --out and zip it for submission."""
    cfg = load_config(config)
    pending = rv.unapproved(cfg.p(cfg.tasks_dir))
    if pending and not allow_unreviewed:
        console.print(f"[red]Not approved yet:[/] {', '.join(pending)}\nRun: taskforge review tasks/<id>")
        raise typer.Exit(code=1)
    out.mkdir(parents=True, exist_ok=True)
    for name in (cfg.tasks_dir, cfg.evidence_dir):
        dst = out / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(cfg.p(name), dst, ignore=shutil.ignore_patterns("_golden", "_probe"))
    zipf = shutil.make_archive(str(out / "taskforge_submission"), "zip", out)
    console.print(f"[green]exported[/] {zipf}")


@app.command("harbor-probe")
def harbor_probe(task: Path = typer.Argument(Path("tasks/_golden")), config: str = CONFIG):
    """Day-1 check on a machine with Docker + Harbor: run nop and oracle once, print what Harbor produced,
    and say whether TaskForge found the reward. Fix `harbor_flags` / validate.find_reward() if it did not."""
    from .validate import harbor, tree_text
    cfg = load_config(config)
    out = cfg.p(cfg.evidence_dir) / "_probe"
    report = [f"# Harbor probe for {task}", ""]
    ok = True
    for agent, want in (("nop", 0.0), ("oracle", 1.0)):
        reward, log = harbor(task, agent, out / agent, cfg.harbor_k, flags=cfg.harbor_flags)
        good = reward == want
        ok &= good
        console.print(f"[{'green' if good else 'red'}]{agent}: reward={reward} (expected {want})[/]")
        report += [f"## {agent}: reward={reward} expected={want} -> {'OK' if good else 'PROBLEM'}", "```",
                   tree_text(out / agent, 60), "```", "console tail:", "```", log[-1500:], "```", ""]
        if reward is None:
            console.print(f"  reward not found. Folder tree:\n{tree_text(out / agent, 40)}\n  Console tail:\n{log[-800:]}")
    write_lf(out / "PROBE_REPORT.md", "\n".join(report))
    console.print(f"report: {out / 'PROBE_REPORT.md'}")
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def run(config: str = CONFIG, tasks: int = typer.Option(5, "--tasks", "-n"), docker: bool = typer.Option(True),
        no_upstream: bool = typer.Option(False, "--no-upstream-check")):
    """Everything: pin -> baseline -> propose -> generate -> validate -> mutate -> summary."""
    cfg = load_config(config)
    out = run_pipeline(cfg, tasks, use_docker=docker, check_upstream=not no_upstream)
    console.print(f"run {out['run_id']} done; see evidence/summary.md")


@app.command()
def doctor(config: str = CONFIG):
    """Check python, git, Docker, Harbor, API keys, Ollama and the critic-family rule on this machine."""
    from .doctor import run_checks
    cfg = load_config(config)
    bad = 0
    for name, ok, detail in run_checks(cfg):
        console.print(f"[{'green' if ok else 'red'}]{'OK ' if ok else 'FAIL'}[/] {name}: {detail}")
        bad += not ok
    raise typer.Exit(code=1 if bad else 0)


@app.command("llm-check")
def llm_check(config: str = CONFIG):
    """Send a one-word prompt to the main and critic models to verify keys / Ollama."""
    cfg = load_config(config)
    warn = llm.check_family(cfg)
    if warn:
        console.print(f"[yellow]{warn}[/]")
    for role in ("main", "critic"):
        m = getattr(cfg.models, role)
        try:
            r = llm.call_llm(f"check_{role}", "Reply with the single word OK.", "ping", m)
            console.print(f"[green]{role}[/] {m.provider}/{m.model}: {r.strip()[:60]!r}")
        except Exception as ex:
            console.print(f"[red]{role}[/] {m.provider}/{m.model}: {ex}")


if __name__ == "__main__":
    app()
