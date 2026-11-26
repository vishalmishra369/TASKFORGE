"""Step 6: write one Harbor task package exactly as in the build guide (section 3)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from . import __version__
from .config import Config

TEMPLATES = Path(__file__).parent / "templates"
LEAK_PATTERNS = [r"test_taskforge", r"test_feature", r"fail_to_pass", r"pass_to_pass", r"solution\.patch",
                 r"\bhidden test", r"\bpytest\b"]


def lint_instruction(text: str) -> list[str]:
    """instruction.md must not leak grader details and must have all required sections."""
    problems = [f"leaks grader detail: /{p}/" for p in LEAK_PATTERNS if re.search(p, text, re.I)]
    for sec in ("Background", "Requirements", "Errors", "Examples", "Out of scope"):
        if not re.search(rf"^##\s*{re.escape(sec)}", text, re.M | re.I):
            problems.append(f"missing section: ## {sec}")
    return problems


def harbor_name(task_id: str) -> str:
    """Harbor requires 'org/name' with name starting alphanumeric (a leading '_' like '_golden' is rejected)."""
    return re.sub(r"^[^A-Za-z0-9]+", "", task_id)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def package(cfg: Config, task_id: str, archetype: str, instruction: str, patch: str, test_code: str,
            f2p: list[str], p2p: list[str], out_root: Path | None = None) -> Path:
    env = Environment(loader=FileSystemLoader(TEMPLATES), keep_trailing_newline=True)
    out = (out_root or cfg.p(cfg.tasks_dir)) / task_id
    if out.exists():
        shutil.rmtree(out)
    for d in ("environment", "solution", "tests"):
        (out / d).mkdir(parents=True)
    common = dict(repo_url=cfg.repo_url, base_commit=cfg.base_commit, tag=cfg.tag)
    (out / "instruction.md").write_text(instruction)
    (out / "task.toml").write_text(env.get_template("task.toml.j2").render(
        **common, namespace=cfg.task_namespace, task_id=harbor_name(task_id), archetype=archetype, version=__version__))
    (out / "environment/Dockerfile").write_text(env.get_template("Dockerfile.j2").render(**common))
    (out / "solution/solution.patch").write_text(patch if patch.endswith("\n") else patch + "\n")
    (out / "solution/solve.sh").write_text(env.get_template("solve.sh.j2").render())
    (out / "tests/test.sh").write_text(env.get_template("test.sh.j2").render(**common))
    shutil.copy(TEMPLATES / "run_eval.py", out / "tests/run_eval.py")
    (out / "tests/test_feature.py").write_text(test_code)
    (out / "tests/fail_to_pass.json").write_text(json.dumps(f2p, indent=1))
    (out / "tests/pass_to_pass.json").write_text(json.dumps(p2p, indent=1))
    for sh in (out / "solution/solve.sh", out / "tests/test.sh"):
        sh.chmod(0o755)
    return out
