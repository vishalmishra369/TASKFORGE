"""Typed configuration loaded from config.yaml (no secrets in here)."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelCfg(BaseModel):
    provider: str = "gemini"
    model: str
    api_key_env: str | None = None
    base_url: str | None = None
    rpm: int = 10
    temperature: float = 0.2

    @property
    def family(self) -> str:
        """Rough model family, used to enforce 'critic != main family'."""
        m = self.model.lower()
        for fam in ("gemini", "gemma", "claude", "gpt", "llama", "qwen", "mistral", "deepseek"):
            if fam in m:
                return "google" if fam in ("gemini", "gemma") else fam
        return self.provider


class Models(BaseModel):
    main: ModelCfg
    critic: ModelCfg


class Config(BaseModel):
    repo_url: str
    tag: str
    base_commit: str
    work_dir: str = "work/click"
    package_dir: str = "src/click"
    tasks_dir: str = "tasks"
    evidence_dir: str = "evidence"
    n_tasks: int = 5
    max_retries: int = 3
    harbor_k: int = 1
    harbor_flags: list[str] = ["-k", "{k}", "--no-delete", "-y"]  # adjust to `harbor run --help`
    semantic_novelty: bool = True
    harbor_enabled: bool = True
    parallel_tasks: int = 2
    baseline_repeats: int = 3
    mutation_runner: str = "local"
    mutation_min_kill_rate: float = 0.8
    task_namespace: str = "hedgeforge"
    models: Models
    root: Path = Field(default=Path("."), exclude=True)

    @field_validator("base_commit")
    @classmethod
    def _full_hash(cls, v: str) -> str:
        if len(v) != 40 or any(c not in "0123456789abcdef" for c in v.lower()):
            raise ValueError("base_commit must be the full 40-char hex hash")
        return v.lower()

    def p(self, rel: str) -> Path:
        return (self.root / rel).resolve()


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    cfg = Config(**data)
    cfg.root = path.resolve().parent
    return cfg


def load_archetypes(path: str | Path = "archetypes.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())
