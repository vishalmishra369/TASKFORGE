# Plan: today (25 Nov 2026) -> finals 20 Dec. About 25 days.

## Day 0-1 (everyone, together)
- [ ] Vinayak: GitHub repo + protection (docs/01), invite team.
- [ ] Everyone: clone, venv, `pip install -e ".[dev,dashboard]"`, `pytest -q` green.
- [ ] Everyone: Docker running, `pip install "harbor==0.25.*"`, `harbor --help`.
- [ ] Nikhil: **run `tasks/_golden` through Harbor** (nop must be 0.0, oracle 1.0). If it fails, fix templates NOW.
- [ ] Yamini + Vinayak: get GEMINI_API_KEY, install Ollama + qwen model, `taskforge llm-check`.

## Week 1 (to ~2 Dec): one task end to end with real LLMs
| Owner | Do | Done when |
|---|---|---|
| Vinayak | Read the Harbor docs; confirm flags in `validate.py`; run `taskforge baseline` in Docker and record excluded tests in evidence/fixes.md | baseline_summary.json shows stable_passing > 0 |
| Vishal | Run `taskforge generate --dry-run`; read candidates.json; tune proposer prompt + archetype rules | 5 picks, one per archetype, plausible, none exist upstream |
| Yamini | Tune spec_writer/implementer/test_author/critic prompts on ONE archetype | one real LLM-built task passes local nop/oracle |
| Nikhil | Harbor gates on that task, flake x3 | `taskforge validate tasks/<id>` all PASS |

## Week 2 (to ~9 Dec): all 5 archetypes
Run `taskforge run -n 5` (overnight if Gemini is slow). Read every failure in `evidence/failures.md`,
fix the GENERATOR (prompt/validator), not the task. Human-verify each final feature against click docs, issues and PRs.
Manual fix needed? Log it in `evidence/fixes.md`.

## Week 3 (to ~16 Dec): proof + polish
- Mutation >= 80% on all five (set `mutation_runner: harbor` in config.yaml once to get official-harness evidence).
- Dashboard review, README tested on a fresh machine, TECHNICAL.md filled with REAL numbers and versions.
- Demo video (<= 5 min): `taskforge run` (cut the waiting) -> dashboard -> open one task -> `harbor` nop 0.0 / oracle 1.0 live.

## Dec 17-19: freeze
Tag `v1.0-submission`, secret scan of history, `taskforge export`, fresh-clone dry run, rehearse the pitch.

## Pitch lines you can truthfully say (after the numbers exist)
"Every task shipped only after: nop = 0.0, oracle = 1.0, three identical oracle runs, >= 80% of deliberate bugs caught,
and an independent critic signing off. Every failed candidate and manual fix is in the evidence folder."
