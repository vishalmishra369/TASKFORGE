# TaskForge (Team HedgeForge, Innodata AI Hackathon, Track 1)

A self-checking factory that turns `pallets/click` at one pinned release into Harbor-ready,
feature-development task packages. **No validation, no package.**

## Quick start
```bash
# prerequisites: Docker running, Python 3.11+, git
git clone <this repo> taskforge && cd taskforge
python -m venv .venv && source .venv/bin/activate        # Windows: use WSL2, or .venv\Scripts\activate
pip install -e ".[dev,dashboard]"
pip install "harbor==0.25.*" && harbor --help           # confirm the CLI
cp .env.example .env && export $(grep -v '^#' .env | xargs)   # put GEMINI_API_KEY in .env first
taskforge doctor                                         # python, git, Docker, Harbor, keys, Ollama: all OK
taskforge llm-check                                      # both models answer "OK"
taskforge run --tasks 5                                  # one command, clean clone -> 5 task folders
streamlit run dashboard/app.py                           # inspect results
```
Expected runtime: set after the first full run (see TECHNICAL.md). The Gemini free tier is rate limited, so the
first run is slow by design (`rpm` in config.yaml).

## Commands
| Command | What it does |
|---|---|
| `taskforge init` | clone, pin base_commit (checks the 40-char hash and the tag), run baseline |
| `taskforge baseline [--no-docker]` | 3x pytest, writes the stable pass list + excluded (flaky/env) tests |
| `taskforge generate --dry-run` | propose + novelty filter only; prints 5 picks, one per archetype |
| `taskforge generate -n 5` | build tasks from the picks |
| `taskforge validate tasks/<id> [--mutation]` / `--all` | Harbor nop / oracle / x3 flake (+ mutants) |
| `taskforge review tasks/<id>` | human sign-off (approve/reject); `--list` shows status |
| `taskforge export --out dist` | tasks + evidence zipped; refuses tasks that are not approved |
| `taskforge harbor-probe` | day-1 check: runs nop + oracle on the golden task and reports what Harbor produced |
| `taskforge doctor` | checks this machine (Docker, Harbor, keys, Ollama, critic family) |
| `taskforge run -n 5` | everything above in one go |
| `taskforge llm-check` | verify keys / Ollama and warn if critic and main share a model family |

## Validate one task by hand
```bash
harbor run -p tasks/<id> -a nop    -k 1 -o out/<id>-nop    --no-delete -y   # expect reward 0.0
harbor run -p tasks/<id> -a oracle -k 1 -o out/<id>-oracle --no-delete -y   # expect reward 1.0
```

## Layout
See CLAUDE.md. `tasks/_golden` is the hand-checked click.Duration template (few-shot example only; it is **not**
one of the 5 submitted tasks). `evidence/` holds Harbor logs, mutation reports, failures.md, fixes.md.

## Switching models (demo -> real deployment)
Edit only the `models:` block in `config.yaml`. See docs/02_LLM_PROVIDERS.md.

## What still needs your machines
See docs/04_REMAINING_FOR_TEAM.md (Harbor run, Docker baseline, first real LLM task, prompt tuning).

## Tests
`pytest -q` (no network/keys/Docker). Full offline pipeline test: `TASKFORGE_E2E=1 pytest tests/test_e2e_mock.py`.
