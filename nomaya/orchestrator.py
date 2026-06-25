"""Orchestrator — the runner at the centre of the MVP architecture.

For each scenario it: builds the agent's system prompt, replays the scripted
customer turns, drives the agent under test through a tool-calling loop in a
sandbox, records the full transcript (text + tool calls + cost/latency), then
hands the transcript to the rules engine and tallies pass/fail.

`run_suite` repeats each scenario `k` times so metrics can report pass@k
reliability — the CLEAR-style insight that an agent passing once may not pass
consistently.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from .agent.compliance_agent import build_system_prompt
from .agent.tools import TOOL_SCHEMAS, execute_tool
from .config import settings
from .logging import get_logger
from .metrics import compute_metrics
from .models import RunResult, Scenario, ScenarioRun, ToolCall, Transcript, Turn, Usage
from .providers.base import LLMProvider, get_provider
from .rules.engine import evaluate

log = get_logger("orchestrator")


def _to_openai_tool_calls(tool_calls: list[dict]) -> list[dict]:
    return [
        {
            "id": tc["id"],
            "type": "function",
            "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments", {}))},
        }
        for tc in tool_calls
    ]


def run_scenario(
    scenario: Scenario,
    agent: LLMProvider,
    judge: LLMProvider | None,
    attempt: int = 0,
) -> ScenarioRun:
    system_prompt = build_system_prompt(scenario)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    turns: list[Turn] = [Turn(role="system", content=system_prompt)]
    usage = Usage()

    for turn_index, customer_msg in enumerate(scenario.customer_turns):
        messages.append({"role": "user", "content": customer_msg})
        turns.append(Turn(role="customer", content=customer_msg))

        agent_tool_calls: list[ToolCall] = []
        final_content = ""

        for _ in range(settings.max_tool_iters):
            resp = agent.complete(
                messages,
                tools=TOOL_SCHEMAS,
                mock_context={"script": scenario.mock, "turn_index": turn_index},
            )
            usage.prompt_tokens += resp.prompt_tokens
            usage.completion_tokens += resp.completion_tokens
            usage.cost_usd += resp.cost_usd
            usage.latency_ms += resp.latency_ms
            usage.model_calls += 1

            if resp.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": resp.content or None,
                        "tool_calls": _to_openai_tool_calls(resp.tool_calls),
                    }
                )
                for tc in resp.tool_calls:
                    try:
                        result = execute_tool(tc["name"], tc.get("arguments", {}), scenario.context)
                    except Exception as exc:  # noqa: BLE001 — a tool fault must not abort the run
                        log.warning("tool %s raised: %s", tc.get("name"), exc)
                        result = {"error": f"tool execution failed: {exc}"}
                    agent_tool_calls.append(
                        ToolCall(name=tc["name"], arguments=tc.get("arguments", {}), result=result)
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result)}
                    )
                if resp.content:  # mock returns text + tool calls together -> turn is done
                    final_content = resp.content
                    break
                # otherwise loop again so a real model can use the tool results
            else:
                final_content = resp.content
                messages.append({"role": "assistant", "content": final_content})
                break

        turns.append(Turn(role="agent", content=final_content, tool_calls=agent_tool_calls))

    transcript = Transcript(turns=turns, usage=usage, model=agent.model)
    check_results = evaluate(scenario.checks, transcript, judge)
    passed = all(r.passed for r in check_results)

    return ScenarioRun(
        scenario_id=scenario.id,
        title=scenario.title,
        label=scenario.label,
        attempt=attempt,
        passed=passed,
        transcript=transcript,
        check_results=check_results,
    )


def run_suite(
    scenarios: list[Scenario],
    agent_model: str | None = None,
    judge_model: str | None = None,
    k: int = 1,
) -> RunResult:
    agent_model = agent_model or settings.agent_model
    judge_model = judge_model or settings.judge_model

    agent = get_provider(agent_model)
    judge = get_provider(judge_model)

    log.info(
        "run start · %d scenarios × k=%d · agent=%s judge=%s",
        len(scenarios), k, agent_model, judge_model,
    )

    scenario_runs: list[ScenarioRun] = []
    for scenario in scenarios:
        for attempt in range(k):
            try:
                sr = run_scenario(scenario, agent, judge, attempt=attempt)
            except Exception as exc:  # noqa: BLE001 — isolate: one scenario must not kill the suite
                log.error("scenario %s attempt %d errored: %s", scenario.id, attempt, exc)
                sr = ScenarioRun(
                    scenario_id=scenario.id,
                    title=scenario.title,
                    label=scenario.label,
                    attempt=attempt,
                    passed=False,
                    transcript=Transcript(model=agent_model),
                    error=f"{type(exc).__name__}: {exc}",
                )
            scenario_runs.append(sr)

    run = RunResult(
        run_id=f"run_{datetime.now(UTC):%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}",
        created_at=datetime.now(UTC).isoformat(),
        agent_model=agent_model,
        judge_model=judge_model,
        scenario_runs=scenario_runs,
    )
    run.metrics = compute_metrics(run, k=k)
    return run
