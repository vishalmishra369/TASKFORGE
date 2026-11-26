# TaskForge, project rules (read before every step)

## Goal
Build "TaskForge": a Python pipeline that reads pallets/click at ONE pinned release commit and automatically
produces 5 Harbor (v0.25.x) task packages that evaluate AI coding agents on FEATURE DEVELOPMENT.
Innodata AI Hackathon, Track 1 (Coding Task Factory). Pinned: click 8.5.1, base_commit in config.yaml.

## Hard rules (from the organisers)
- New features or changed behaviour only. NO bug-fix tasks.
- Every task starts from the same real commit; full 40-char hash in task.toml as base_commit.
- Generated features must NOT already exist upstream in click (tag AND main).
- 5 tasks differ in behaviour/rules/interactions, not wording. One per archetype (archetypes.yaml).
- Task folder = instruction.md, solution/ (solve.sh + solution.patch), tests/ (test.sh, run_eval.py,
  test_feature.py, fail_to_pass.json, pass_to_pass.json), environment/Dockerfile, task.toml.
- instruction.md is the ONLY file the solver sees. Every tested behaviour must be stated in it.
- Reward: 0.0 if any pass_to_pass fails; else share of fail_to_pass passing -> /logs/verifier/reward.txt.
- `harbor -a nop` must give 0.0; `harbor -a oracle` must give 1.0.
- Tests: pytest + CliRunner, no network, no credentials, no sleeps, no randomness; import new APIs INSIDE tests.
- If the organisers' task interface differs from this repo on any detail, THEIRS WINS.

## Architecture
Orchestrator -> Repo Intelligence -> Proposer -> Novelty filter -> Spec writer -> Implementer -> Test author ->
Critic (different model family, veto) -> Packager -> Validator (nop, oracle, x3 flake, mutation) -> human review -> export.
Failed gate -> error log goes back to the failing agent, max 3 tries, next-best candidate, then drop + log.

## Engineering rules
- Python 3.11+, Typer CLI, Pydantic config, Jinja2 templates.
- ALL LLM calls go through taskforge/llm.py (provider-agnostic: gemini | ollama | openai-compatible | anthropic | mock).
- API keys only from env vars; never in files, logs or git history.
- Same config + same commit = same pipeline steps. Unit tests never call real LLMs or the network.
- Log every manual fix in evidence/fixes.md. Fix the generator, not the generated task.
- Keep functions small. Plain files (JSON/TOML/MD), no databases.
- Never mention model names in agent prompts' logic; models are chosen in config.yaml only.
