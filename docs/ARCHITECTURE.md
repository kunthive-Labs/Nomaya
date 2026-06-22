# Nomaya — Architecture & Extension Guide

## Data flow

```
playbook.yaml ──load──▶ Scenario ──┐
                                    ▼
                          Orchestrator.run_scenario
                                    │  builds system prompt, replays customer turns
                                    ▼
                     LLMProvider.complete (agent under test)   ◀── tool loop ──▶ agent/tools.execute_tool
                                    │  records Transcript (turns + tool calls + usage)
                                    ▼
                          rules.engine.evaluate ──per-check──▶ rules/checks.py
                                    │                            │ NO_PII_LEAK ─▶ rules/pii.py
                                    │                            │ LLM_JUDGE   ─▶ LLMProvider (judge)
                                    ▼
                          ScenarioRun (pass/fail + CheckResults)
                                    ▼
        run_suite collects all ScenarioRuns ──▶ metrics.compute_metrics ──▶ RunResult
                                                                                │
                                          ┌─────────────────────────────────────┼───────────────┐
                                          ▼                                     ▼               ▼
                                   store.save_run (SQLite)            report.write_reports   api → dashboard
```

The orchestrator is the only component that knows the full pipeline. Everything
else is a pure, independently-testable unit: providers, checks, the PII detector,
and metrics never import each other sideways.

## The provider seam

`nomaya/providers/base.py` defines one interface — `complete(messages, tools)`.
`get_provider(model)` routes `mock/...` to the deterministic in-process provider
and everything else through LiteLLM. **Adding a lab is a config string, not code.**
Any LiteLLM-supported model works as the agent under test or the judge:
`openai/...`, `anthropic/...`, `gemini/...`, `mistral/...`, `cohere/...`,
`groq/...`, `bedrock/...`, `ollama/...`.

## Extending Nomaya

**Add a regulation** — append an entry to `nomaya/regulations/registry.yaml`.
Reference its `id` from any check; reports and the dashboard group by it
automatically.

**Add a scenario** — drop a YAML file in `nomaya/scenarios/playbooks/`. Set its
`label` (`violation_expected` to tempt a violation, or `benign_control` to guard
against false positives), list `customer_turns`, define `checks`, and provide
`mock.compliant` / `mock.naive` scripts so it runs in deterministic mode.

**Add a check type** — add a member to `CheckType` (`models.py`), implement an
evaluator in `rules/checks.py`, and wire it into the dispatch in
`rules/engine.py`. Checks receive the whole `Transcript`, so they can inspect
agent text, all turns, or tool calls.

**Strengthen PII detection** — `rules/pii.py` is regex + Luhn today; the
`detect_pii` signature is the seam to drop in an ML recognizer (e.g. Presidio)
without touching the engine.

## Design choices worth noting

- **Ground-truth labels drive precision/recall.** `benign_control` scenarios are
  how false-positive rate stays honest — a harness that flags everything would
  score 100% detection but blow up FP rate.
- **pass@k over pass@1.** A model that complies once may not comply consistently.
  Running each scenario `k` times surfaces the reliability drop that a single
  attempt hides.
- **Deterministic mock mode is a first-class path, not a stub.** It lets the
  *harness itself* be regression-tested in CI (clears the good agent, catches the
  bad one) with zero token spend — the property that makes this CI-gateable.
