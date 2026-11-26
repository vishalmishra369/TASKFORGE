# Models: Gemini for the demo, self-hosted for the real thing

Everything goes through `taskforge/llm.py`. Switching = edit the `models:` block of `config.yaml`. No code changes.
Providers: `gemini`, `ollama`, `openai` (any OpenAI-compatible server: vLLM, llama.cpp server, LM Studio,
Groq/OpenRouter-style gateways), `anthropic`, `mock` (tests).

## A. Demo setup (free): Gemini main + local Ollama critic
Why the critic is local: the deck promises an independent critic from a *different model family*. If Gemini grades
Gemini, that claim is false. A small local model from another family (Qwen) costs nothing.

1. Gemini key: https://aistudio.google.com -> "Get API key". Put it in `.env` as `GEMINI_API_KEY=...`.
   Load it: `export $(grep -v '^#' .env | xargs)` (PowerShell: `$env:GEMINI_API_KEY="..."`).
2. In AI Studio check which model names your key can use and the free-tier limits (they change; do not trust
   old blog posts). Put the name in `models.main.model` and set `rpm` below the limit (config default is 8).
   Limits apply per Google Cloud project, not per key, and the daily quota resets at midnight Pacific.
3. Ollama: install from ollama.com, then `ollama pull qwen2.5-coder:7b` (about 5 GB; needs ~8 GB RAM free).
4. Verify: `taskforge llm-check` must print OK for both lines and no family warning.

## B. All-local (no internet, no limits, slower/weaker)
```yaml
models:
  main:   { provider: ollama, model: "qwen2.5-coder:32b", base_url: "http://localhost:11434", rpm: 0 }
  critic: { provider: ollama, model: "llama3.1:8b",       base_url: "http://localhost:11434", rpm: 0 }
```
The 32B model needs roughly 20+ GB of GPU/unified memory at 4-bit. If you only have a laptop, keep Gemini as main.

## C. Real deployment on a server
Run a GPU box (Ollama, or vLLM for throughput) and point TaskForge at it:
```yaml
models:
  main:   { provider: openai, model: "<model served by vLLM>", base_url: "http://gpu-server:8000/v1", rpm: 0 }
  critic: { provider: ollama, model: "<different family>",     base_url: "http://gpu-server:11434", rpm: 0 }
```
Put the server behind your VPN/firewall; never expose an unauthenticated model port to the internet.
Add `api_key_env` if the gateway needs a token. Use the strongest model you can host for `main`: the implementer must
emit exact search/replace edits and weak models fail that often (retries absorb some of it).

## D. What to say in TECHNICAL.md and the video
"TaskForge is model-agnostic. The hackathon run used Gemini (free tier) as the generator and a local Qwen model as the
independent critic. A production deployment swaps both for self-hosted models through the same config block."
List the exact model names and versions you actually used. Never claim a model you did not run.

## E. Cost/limit tricks already built in
`rpm` self-throttle, automatic 429 backoff, repo map cached per commit, heuristic novelty filter (no LLM calls),
local mutation runner, retries capped at 3, every call logged in `runs/<id>/llm_log.jsonl` (prompt, tokens, latency).
