# What is left for YOU (needs Docker, Harbor runs, or a real model key)

Everything else is written and tested (see `pytest -q`). These items cannot be done without your machines.
Work top to bottom. Each has the exact command, what "good" looks like, and where to fix things if it fails.

## 0. Everyone, 10 minutes
```bash
pip install -e ".[dev]" "harbor==0.25.*"   # add: pip install streamlit  (optional dashboard)
cp .env.example .env   # add GEMINI_API_KEY, then: export $(grep -v '^#' .env | xargs)
taskforge doctor       # every line must say OK
pytest -q              # all green (3 tests skip unless harbor/streamlit/click clone are present)
```

## 1. Harbor integration (Nikhil + Vinayak)
```bash
taskforge harbor-probe tasks/_golden
```
Good: `nop: reward=0.0` and `oracle: reward=1.0`. The report is in `evidence/_probe/PROBE_REPORT.md`.
Already verified for you against harbor 0.25.0: flags `-p -a -k -o --no-delete -y` exist, agents `nop` and `oracle`
exist, `task.toml` schema 1.3 loads, rewards are read from `verifier/reward.txt` / `reward.json` /
`result.json -> verifier_result.rewards`. NOT verified: an actual container run.
If reward is `None`: open the printed folder tree, find where Harbor wrote the verifier output, and extend
`find_reward()` in `taskforge/validate.py` (add a test next to the others in `tests/test_validate_harbor.py`).
If a flag is rejected: change `harbor_flags` in `config.yaml` (no code change).

## 2. Docker baseline (Vinayak)
```bash
taskforge baseline            # builds the image from Dockerfile.j2 and runs pytest 3x inside it
cat runs/baseline/baseline_summary.json runs/baseline/baseline_excluded.json
```
Good: `stable_passing` in the thousands; few or no excluded tests. Pager tests excluded? Check that `less` installed
(Dockerfile.j2). Write what was excluded and why into `evidence/fixes.md` and mention it in TECHNICAL.md.
If the image build fails, fix `taskforge/templates/Dockerfile.j2` only.

## 3. First real LLM task (Yamini)
```bash
taskforge llm-check
taskforge generate --dry-run              # look at runs/<id>/candidates.json first
taskforge generate -n 1 -a new_param_type # first real task, Harbor on
```
Read `evidence/<task>/attempts.jsonl` and `runs/<id>/llm_log.jsonl` (every prompt and answer is logged).
Fix the PROMPTS in `taskforge/agents/*.py` and `archetypes.yaml`, not the generated task. Implementer edits that do
not match are retried once as whole-file output automatically; patches over 450 changed lines are rejected.
Gemini blocks/empties/truncations are retried as normal failed tries.

## 4. Prompt tuning rounds (Yamini + Vishal)
Run all five (`taskforge run -n 5`), read `evidence/failures.md`, adjust prompts, repeat. Typical fixes:
spec leaves a boundary open (add a rule to `spec_writer.SYSTEM`), tests check unstated text (tighten `critic.SYSTEM`),
candidates too big (lower `est_lines` guidance in `proposer.SYSTEM`).

## 5. Human review and official mutation evidence
```bash
taskforge review tasks/<id>                # shows the card, asks to approve; --approve --by NAME also works
taskforge validate --all --mutation        # set mutation_runner: harbor in config.yaml once for official evidence
taskforge export --out dist                # refuses until every task is approved
```
Approval is bound to file hashes: edit a task after sign-off and it becomes `stale` and must be re-approved.
Review checklist: is the feature truly absent upstream (check click docs, issues and PRs), does instruction.md state
every tested behaviour and exact error text, no network/credentials in tests.

## 6. Final
Fill the TODOs in TECHNICAL.md with REAL numbers and model versions, record the demo, fresh-machine README run,
secret scan of git history (docs/01_GITHUB_SETUP.md section 7).
