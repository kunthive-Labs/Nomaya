# Nomaya

**A provider-agnostic compliance evaluation suite for AI agents in financial services.**

Generic LLM evals miss the subtle, high-stakes failures that matter in regulated
finance — leaking nonpublic personal information, omitting a required Truth-in-Lending
disclosure, making a UDAAP-deceptive statement about fees, or acting on a transfer
without authorization. Nomaya is a purpose-built harness that runs an AI customer-service
agent through regulation-mapped scenarios in a sandbox and checks its behavior against
named obligations (GLBA, UDAAP, Reg Z, Reg E, FCRA, ECOA, SR 11-7, NYDFS 500, EU AI Act, DORA).

It is **provider-agnostic**: the agent under test and the LLM-judge can be any leading
lab's model — OpenAI, Anthropic, Google, Mistral, Cohere, Groq, or a local model via
Ollama — reached through one interface (LiteLLM). With no API keys set, it runs fully
offline in deterministic **mock** mode, which is what makes it CI- and demo-friendly.

```
   Scenario DB ──▶ Orchestrator ──▶ Agent (sandbox) ──▶ Backend tools
                        │                                    │
                        ▼                                    │
                   Rules Engine ◀───────── transcript ───────┘
                  (+ PII detector,
                   + LLM-judge)
                        │
                        ▼
                  Metrics ──▶ Report (HTML/JSON) + Dashboard (Next.js)
```

## Quick start

```bash
uv sync --locked          # installs Python 3.12 + pinned deps from uv.lock
source .venv/bin/activate

# Run the full suite in deterministic mock mode (no API key needed)
nomaya run                               # compliant agent  -> high pass rate
nomaya run --agent mock/naive-agent      # naive agent      -> violations caught

# Point it at a real model from any lab (set the matching key in .env)
nomaya run --agent openai/gpt-4o-mini --judge openai/gpt-4o-mini
nomaya run --agent anthropic/claude-haiku-4-5
nomaya run --agent gemini/gemini-2.0-flash
nomaya run --agent ollama/llama3.1       # fully local

# Reliability: run each scenario k times, report the pass@k drop
nomaya run --k 5

# CI gating: fail on pass rate and/or the severity-weighted score
nomaya run --fail-under 1.0 --fail-under-weighted 1.0

# Other commands
nomaya scenarios      # list playbooks
nomaya regulations    # list the regulation registry
nomaya list           # past runs
nomaya serve          # dashboard API on :8000
```

## Dashboard

```bash
nomaya serve                             # FastAPI on :8000 (terminal 1)
cd dashboard && npm install && npm run dev   # Next.js on :3000 (terminal 2)
```

The dashboard reaches the API through a server-side proxy
(`dashboard/app/api/[...path]/route.ts`), so if the API has a bearer token the
token stays out of the browser. Configure via `dashboard/.env.local` (copy from
`.env.local.example`).

Or run both with Docker:

```bash
docker compose up --build      # API on :8000, dashboard on :3000
```

## Configuration

Copy `.env.example` to `.env`. Besides provider keys, the notable variables:

| Variable | Default | Meaning |
|---|---|---|
| `NOMAYA_AGENT_MODEL` | `mock/compliant-agent` | Default agent under test. |
| `NOMAYA_SUITE_VERSION` | `2026.1` | Version recorded with each run for reproducibility. |
| `NOMAYA_JUDGE_MODEL` | `mock/judge` | Default LLM-judge. |
| `NOMAYA_DB_PATH` | `<repo>/nomaya.sqlite3` | SQLite run history. |
| `NOMAYA_STORAGE_REDACT_PII` | `true` | Redact detected PII and secret-like tool fields before saving history or report artifacts. |
| `NOMAYA_ENFORCE_PRIVATE_STORAGE` | `true` | Set SQLite database file permissions to owner-only on POSIX. |
| `NOMAYA_RETENTION_DAYS` | *(unset)* | Delete saved runs older than this many days when a new run is saved. |
| `NOMAYA_ENV` | `development` | Set to `production` to require API authentication and reject wildcard model/CORS allow-lists. |
| `NOMAYA_API_TOKEN` | *(empty — auth off)* | Bearer token for every API route except `/api/health`. |
| `NOMAYA_READ_TOKEN` / `NOMAYA_RUN_TOKEN` / `NOMAYA_ADMIN_TOKEN` | *(empty)* | Optional scoped bearer tokens for viewing, running, and administering evaluations. |
| `NOMAYA_ALLOWED_MODELS` | mock models only | Models `POST /api/run` may target; `*` allows any. Protects against strangers burning your provider credits. |
| `NOMAYA_CORS_ORIGINS` | localhost:3000 | Browser origins allowed by CORS (direct mode only). |
| `NOMAYA_DB_TIMEOUT` | `5.0` | SQLite database connection timeout in seconds. |
| `NOMAYA_MAX_CONCURRENT_RUNS` | `2` | Maximum in-process evaluation jobs running at once. |
| `NOMAYA_MAX_QUEUED_RUNS` | `20` | Maximum queued plus running jobs. |
| `NOMAYA_MAX_RUN_SCENARIOS` | `100` | Upper bound on scenarios × attempts accepted by the API. |
| `NOMAYA_MAX_RUN_COST_USD` | `0` | Per-run provider-cost cap; `0` disables the cap. |
| `NOMAYA_MAX_RUN_DURATION_SECONDS` | `900` | Per-run wall-clock cap; `0` disables it. |

The API supports synchronous compatibility at `POST /api/run` and background
evaluation at `POST /api/jobs`, with status at `GET /api/jobs/{job_id}` and
cooperative cancellation at `DELETE /api/jobs/{job_id}`. Read the
[operations guide](docs/OPERATIONS.md) before exposing the service, and use the
[evaluation-governance guide](docs/EVALUATION_GOVERNANCE.md) to manage approved
scenario suites and release evidence.

## What it measures

| Metric | Meaning |
|---|---|
| **Pass rate** | Scenario runs with zero violations. |
| **Violation detection rate** | Of scenarios that tempt a violation, how many were flagged (recall — measure against a non-compliant agent). |
| **False-positive rate** | Of benign control scenarios, how many were wrongly flagged (precision proxy). |
| **Weighted score** | 1 − (severity weight of failed checks ÷ total possible weight); a critical PII leak costs far more than an info-level nit. Gate with `--fail-under-weighted`. |
| **Compliance coverage** | Distinct regulations exercised ÷ regulations known. |
| **pass@k reliability** | Fraction passing *all* k attempts vs any; the gap is the reliability drop (CLEAR-style). |
| **Cost & latency** | $/run and throughput, summed from provider usage. |

## How a scenario works

Each YAML playbook (`nomaya/scenarios/playbooks/`) defines the customer turns, the
account fixture handed to the agent's sandboxed tools, and a list of declarative
**checks** mapped to regulations. Check types: `required_phrase`, `prohibited_phrase`,
`regex`, `no_pii_leak`, `tool_call_expected`, `tool_call_forbidden`, and `llm_judge`
for subjective rules. A scenario passes only if every check passes.

Playbooks also ship deterministic `compliant` / `naive` mock scripts so the harness
itself can be regression-tested in CI — proving Nomaya clears a good agent and catches
a bad one without spending tokens.

## Architecture

| Path | Role |
|---|---|
| `nomaya/providers/` | One `LLMProvider` interface; LiteLLM adapter (all labs) + deterministic mock. |
| `nomaya/agent/` | Agent-under-test system prompt + sandboxed backend tools. |
| `nomaya/rules/` | Rules engine, per-check evaluators, PII/NPI detector. |
| `nomaya/regulations/` | Regulation registry (`registry.yaml`) + loader. |
| `nomaya/scenarios/` | Playbook loader + YAML scenarios. |
| `nomaya/orchestrator.py` | The runner: drives the agent, records transcripts, evaluates. |
| `nomaya/metrics.py` | All success metrics, incl. pass@k reliability. |
| `nomaya/report.py` · `store.py` · `api.py` · `cli.py` | Reporting, SQLite history, API, CLI. |
| `dashboard/` | Next.js dashboard. |

> **Note:** Regulation summaries are paraphrased for orientation and are **not legal
> advice**. Mappings should be reviewed by qualified compliance/legal staff before relying
> on them for a deployment decision.

## License

MIT
