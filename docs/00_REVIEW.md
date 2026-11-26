# Review of the idea deck + build guide (what I checked, what I changed)

Verified by actually running things on click 8.5.1 and against the real `harbor==0.25.0` package (newest tag, released 2026-11-09,
commit `cf19179e8e2fd54c601378cec9e0d21bb12b6fb1`). NOT verified: any container run (no Docker in my sandbox): Harbor nop/oracle runs, the Docker baseline, and real LLM calls.

## Strong points
- "No validation, no package" + nop/oracle/mutation/critic is a real differentiator. Keep it as the headline.
- Deck, guide and CLAUDE.md agree with each other; the 8-step flow and owners are clear.

## Problems found and how the code handles them
| # | Finding | Fix in this repo |
|---|---|---|
| 1 | Guide says changelog is `CHANGES.rst`; click 8.5.1 uses `CHANGES.md` | novelty.py checks both |
| 2 | Guide example tag "8.3.x" is stale; newest is 8.5.1 | config.yaml pins 8.5.1 + hash; baseline checks tag == hash |
| 3 | "Baseline must be all green" is false out of the box: pager tests (`test_echo_via_pager.py`) fail without `less`/TTY (24 failed in my sandbox; 49 tests were flaky/failing across 3 runs) | Dockerfile installs `less`; baseline runs 3x and keeps only tests that pass every time; the rest go to `baseline_excluded.json` (logged, never hidden). Ask the organisers if exclusions are OK; log in fixes.md |
| 4 | Dockerfile clones full click history. A solver can `git log --all` and read upstream's real implementation | Dockerfile deletes remote, refs and unreachable objects after checkout |
| 5 | Guide's run_eval passes thousands of node IDs on the command line; IDs with spaces/brackets (`test_x[1 h]`) are fragile; division by zero if F2P empty; one collection error aborts the run | run_eval.py runs `tests/` once with `--continue-on-collection-errors` and looks results up by node ID |
| 6 | test.sh restores tests/ but leaves files the solver added under tests/ | added `git clean -fdq tests/` |
| 7 | Novelty only vs the tag is not enough ("must not exist upstream") | also greps `origin/main`; heuristic only, so a HUMAN must still check the final 5 against click docs/issues/PRs |
| 8 | Naive name matching rejected valid ideas (`section` collides with `HelpFormatter.section`) | novelty classifies CamelCase (class) vs snake_case (function/kwarg) |
| 9 | click 8.5 types are generic (`ParamType[str]`), so a naive AST scan finds zero ParamType subclasses | repo_intel strips subscripts |
| 10 | Mutating docstring lines gives unkillable mutants (golden task scored 50% for the wrong reason) | mutator skips docstrings: golden task now 90% (9/10) |
| 11 | "Critic from a different model family" breaks if everything runs on Gemini | critic defaults to a local Ollama model; `llm-check` warns when families match |
| 12 | Deck says Claude orchestrates; the demo will use Gemini | be honest in TECHNICAL.md + video: the pipeline is model-agnostic, Gemini for demo, self-hosted for real use |
| 13 | Deck slide 6 shows `taskforge init --repo ... --ref <tag>`; guide uses config.yaml | CLI reads config.yaml (`--config`); update the slide mock or accept the small mismatch |
| 14 | Slide 14 of the deck is empty | delete or fill |
| 15 | Harbor rejects task names starting with `_` (`hedgeforge/_golden` is invalid; found by loading the task in Harbor's own model) | packager strips leading non-alphanumerics from the Harbor name; golden is `hedgeforge/golden` |
| 16 | Gemini can return no candidates / blocked / truncated / empty text, which would crash with `KeyError` | all become `LLMError`; a failed try is retried, never a crashed run |
| 17 | Review step existed only on the slide ("human sign-off") | `taskforge review` + `export` refuses unapproved/rejected/stale tasks (approval is tied to file hashes) |
| 18 | Name-based novelty cannot catch the same idea under another name | optional LLM duplicate check by the independent critic model (`semantic_novelty` in config; fails open) |

## Golden task (tasks/_golden, click.Duration), proven locally
23 feature tests all FAIL without the patch; with it reward = 1.0 (23 F2P + 2410 P2P); mutation 9/10 killed
(the survivor is `__repr__`, which the spec does not define). The only real mutation weakness found was a loose
`pytest.raises(match=...)` for the ValueError text, tightened to an exact comparison.

## Open risks (do these early)
1. **Run `taskforge harbor-probe` on a Docker machine on day 1** (docs/04_REMAINING_FOR_TEAM.md). I verified the flags,
   the agents, the schema and the reward-file layout against the harbor 0.25.0 package, but not a container run.
2. Docker build clones GitHub at build time: judges' machine needs network for the build.
3. LLM quality: implementer must return exact search/replace edits; small local models fail this often.
   Use the strongest model you have for `implementer`, retries absorb the rest.
4. Gemini free tier is per project, not per key; limits and model names change. Check AI Studio's rate-limit page
   before the run; keep `rpm` low; run overnight if needed.
5. Semantic duplicates upstream (the idea exists under another name) are not caught by name matching.
