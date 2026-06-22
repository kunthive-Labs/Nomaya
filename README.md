# Nomaya

**A provider-agnostic compliance evaluation suite for AI agents in financial services.**

Generic LLM evals miss the subtle, high-stakes failures that matter in regulated
finance — leaking nonpublic personal information, omitting a required Truth-in-Lending
disclosure, making a UDAAP-deceptive statement about fees, or acting on a transfer
without authorization. Nomaya is a purpose-built harness that runs an AI customer-service
agent through regulation-mapped scenarios in a sandbox and checks its behavior against
named obligations (GLBA, UDAAP, Reg Z, Reg E, FCRA, ECOA, SR 11-7, NYDFS 500, EU AI Act).

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
uv venv --python 3.12 && uv pip install -e ".[dev]"
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

# Other commands
nomaya scenarios      # list playbooks
nomaya regulations    # list the regulation registry
nomaya list           # past runs
nomaya serve          # dashboard API on :8000
```

## What it measures

| Metric | Meaning |
|---|---|
| **Pass rate** | Scenario runs with zero violations. |
| **Violation detection rate** | Of scenarios that tempt a violation, how many were flagged (recall — measure against a non-compliant agent). |
| **False-positive rate** | Of benign control scenarios, how many were wrongly flagged (precision proxy). |
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
