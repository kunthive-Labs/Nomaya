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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from .agent.compliance_agent import PROMPT_VERSION, build_system_prompt
from .agent.tools import TOOL_SCHEMA_VERSION, TOOL_SCHEMAS, execute_tool
from .config import settings
from .metrics import compute_metrics
from .models import RunResult, Scenario, ScenarioRun, ToolCall, Transcript, Turn, Usage
from .providers.base import LLMProvider, get_provider
from .rules.engine import evaluate

MAX_TOOL_ITERS = 5


class EvaluationCancelled(Exception):
    """Raised when a queued/running evaluation has been cancelled."""


class EvaluationLimitExceeded(Exception):
    """Raised when an evaluation exceeds its configured budget or deadline."""


@dataclass(frozen=True)
class RunLimits:
    """Cooperative limits checked between provider calls and scenarios."""

    max_cost_usd: float = 0.0
    max_duration_seconds: float = 0.0
    cancelled: Callable[[], bool] | None = None


def _check_limits(limits: RunLimits, started_at: float, cost_usd: float = 0.0) -> None:
    if limits.cancelled and limits.cancelled():
        raise EvaluationCancelled("Evaluation was cancelled.")
    if limits.max_duration_seconds and monotonic() - started_at > limits.max_duration_seconds:
        raise EvaluationLimitExceeded("Evaluation exceeded its duration limit.")
    if limits.max_cost_usd and cost_usd > limits.max_cost_usd:
        raise EvaluationLimitExceeded("Evaluation exceeded its cost limit.")


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
    limits: RunLimits | None = None,
    started_at: float | None = None,
) -> ScenarioRun:
    limits = limits or RunLimits()
    started_at = started_at if started_at is not None else monotonic()
    system_prompt = build_system_prompt(scenario)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    turns: list[Turn] = [Turn(role="system", content=system_prompt)]
    usage = Usage()

    for turn_index, customer_msg in enumerate(scenario.customer_turns):
        messages.append({"role": "user", "content": customer_msg})
        turns.append(Turn(role="customer", content=customer_msg))

        agent_tool_calls: list[ToolCall] = []
        final_content = ""

        for _ in range(MAX_TOOL_ITERS):
            _check_limits(limits, started_at, usage.cost_usd)
            resp = agent.complete(
                messages,
                tools=TOOL_SCHEMAS,
                mock_context={"script": scenario.mock, "turn_index": turn_index},
            )
            usage.add(
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                cost_usd=resp.cost_usd,
                latency_ms=resp.latency_ms,
            )
            _check_limits(limits, started_at, usage.cost_usd)

            if resp.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": resp.content or None,
                        "tool_calls": _to_openai_tool_calls(resp.tool_calls),
                    }
                )
                for tc in resp.tool_calls:
                    result = execute_tool(tc["name"], tc.get("arguments", {}), scenario.context)
                    agent_tool_calls.append(ToolCall(name=tc["name"], arguments=tc.get("arguments", {}), result=result))
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result)})
                if resp.content:  # mock returns text + tool calls together -> turn is done
                    final_content = resp.content
                    break
                # otherwise loop again so a real model can use the tool results
            else:
                final_content = resp.content
                messages.append({"role": "assistant", "content": final_content})
                break

        turns.append(Turn(role="agent", content=final_content, tool_calls=agent_tool_calls))

    transcript = Transcript(turns=turns, usage=usage, agent_usage=usage.model_copy(deep=True), model=agent.model)
    _check_limits(limits, started_at, transcript.usage.cost_usd)
    check_results = evaluate(scenario.checks, transcript, judge)
    _check_limits(limits, started_at, transcript.usage.cost_usd)
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
    max_cost_usd: float = 0.0,
    max_duration_seconds: float = 0.0,
    cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> RunResult:
    agent_model = agent_model or settings.agent_model
    judge_model = judge_model or settings.judge_model

    agent = get_provider(agent_model)
    judge = get_provider(judge_model)
    limits = RunLimits(
        max_cost_usd=max_cost_usd,
        max_duration_seconds=max_duration_seconds,
        cancelled=cancelled,
    )
    started_at = monotonic()
    total_cost = 0.0
    total_work = len(scenarios) * k

    scenario_runs: list[ScenarioRun] = []
    for scenario in scenarios:
        for attempt in range(k):
            _check_limits(limits, started_at, total_cost)
            scenario_run = run_scenario(
                scenario,
                agent,
                judge,
                attempt=attempt,
                limits=limits,
                started_at=started_at,
            )
            scenario_runs.append(scenario_run)
            total_cost += scenario_run.transcript.usage.cost_usd
            _check_limits(limits, started_at, total_cost)
            if on_progress:
                on_progress(len(scenario_runs), total_work)

    run = RunResult(
        run_id=f"run_{datetime.now(UTC):%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}",
        created_at=datetime.now(UTC).isoformat(),
        agent_model=agent_model,
        judge_model=judge_model,
        configuration={
            "suite_version": settings.suite_version,
            "prompt_version": PROMPT_VERSION,
            "tool_schema_version": TOOL_SCHEMA_VERSION,
            "k": k,
            "scenario_ids": [scenario.id for scenario in scenarios],
            "scenario_tags": sorted({tag for scenario in scenarios for tag in scenario.tags}),
            "max_cost_usd": max_cost_usd,
            "max_duration_seconds": max_duration_seconds,
        },
        scenario_runs=scenario_runs,
    )
    run.metrics = compute_metrics(run, k=k)
    return run
