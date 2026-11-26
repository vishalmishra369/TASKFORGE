# TaskForge, technical document (fill the TODOs from real runs)

## 1. Design
Orchestrator + specialist agents + independent critic with veto, same pattern as our HedgeForge entry.
Pipeline: pin commit -> baseline -> repo map -> propose -> novelty filter -> spec -> implement -> tests -> critic ->
package -> Harbor nop/oracle -> flake x3 -> mutation -> manifest. Failed gate -> error log back to the agent (max 3).

## 2. Assumptions
- One repo (pallets/click) at tag 8.5.1, base_commit cf19179e8e2fd54c601378cec9e0d21bb12b6fb1 (verify in your clone).
- Baseline: pass_to_pass = tests that passed in 3 consecutive runs; excluded tests are listed in
  runs/<id>/baseline_excluded.json (TODO: paste count and reason from your Docker run).
- Environment-dependent tests (pager tests need `less`) are handled by installing `less` in the image; TODO confirm.

## 3. Models and tools (declare EVERY one, with version)
| Role | Demo run | Real deployment | Version |
|---|---|---|---|
| main (propose/spec/implement/test) | Gemini API (free tier) | self-hosted via Ollama or vLLM | TODO |
| critic (different family) | Ollama qwen2.5-coder:7b | self-hosted, different family from main | TODO |
| Claude Code | used to write pipeline code from CLAUDE.md prompts | | TODO |
Tools: Python, Typer, Pydantic, Jinja2, httpx, git, Docker, Harbor 0.25.x, pytest, pytest-json-report, Streamlit.

## 4. Variation strategy
Five archetypes (archetypes.yaml): new_param_type, new_command_behaviour, change_existing_behaviour,
feature_interaction, new_validation_rule. One task per archetype; Jaccard similarity > 0.6 between candidates rejects.

## 5. Validation matrix
Baseline green, nop 0.0, oracle 1.0, oracle x3 identical, mutation kill rate >= 80%, critic approval,
no network/credentials in tests. TODO: table of the 5 tasks with real numbers from evidence/summary.md.

## 6. Mutation results / known failures / manual fixes
TODO: link evidence/<id>/validation.md, evidence/failures.md, evidence/fixes.md.
Known limitation: mutation uses a line-level mutator; some survivors are spec-equivalent (e.g. __repr__).
