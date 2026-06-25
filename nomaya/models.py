"""Core domain models for Nomaya.

These pydantic models are the contract shared by every layer: scenario loading,
the agent runner, the rules engine, metrics, and reporting. Keep them free of
behaviour so they serialize cleanly to JSON for the dashboard and CI artifacts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    """How serious a failed compliance check is. Drives gating and weighting."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        return {"info": 0, "low": 1, "medium": 3, "high": 7, "critical": 15}[self.value]


class CheckType(str, Enum):
    """The kinds of rules the engine knows how to evaluate."""

    REQUIRED_PHRASE = "required_phrase"      # agent MUST surface this disclosure
    PROHIBITED_PHRASE = "prohibited_phrase"  # agent must NOT say this
    REGEX = "regex"                          # arbitrary pattern, present or absent
    NO_PII_LEAK = "no_pii_leak"              # agent must not expose protected data
    TOOL_CALL_EXPECTED = "tool_call_expected"  # agent must call a backend tool (e.g. log reasoning)
    TOOL_CALL_FORBIDDEN = "tool_call_forbidden"  # agent must NOT call a tool (e.g. unauthorized transfer)
    LLM_JUDGE = "llm_judge"                  # subjective rule graded by an LLM-judge


class ScenarioLabel(str, Enum):
    """Ground-truth label used to compute precision / false-positive rate."""

    VIOLATION_EXPECTED = "violation_expected"  # a correct agent should NOT trip this; a bad one will
    BENIGN_CONTROL = "benign_control"          # a correct agent passes cleanly; flags here are false positives


# --------------------------------------------------------------------------- #
# Regulations
# --------------------------------------------------------------------------- #
class Regulation(BaseModel):
    """A regulatory obligation a check maps to. Loaded from regulations/registry.yaml."""

    id: str
    name: str
    authority: str = ""
    summary: str = ""
    url: str = ""


# --------------------------------------------------------------------------- #
# Checks (declarative, authored in scenario YAML)
# --------------------------------------------------------------------------- #
class Check(BaseModel):
    """A single declarative compliance assertion against a transcript."""

    id: str
    type: CheckType
    description: str = ""
    regulations: list[str] = Field(default_factory=list)  # regulation ids
    severity: Severity = Severity.MEDIUM

    # type-specific configuration (only the relevant ones are read per type)
    patterns: list[str] = Field(default_factory=list)   # phrases / regexes / tool names
    case_sensitive: bool = False
    must_appear: bool = True            # for REGEX: True => must match, False => must NOT match
    scope: Literal["agent", "all"] = "agent"  # which transcript turns to scan
    pii_types: list[str] = Field(default_factory=list)  # for NO_PII_LEAK; empty => all types
    rubric: str = ""                    # for LLM_JUDGE: what the judge must decide
    judge_pass_if: str = "yes"          # judge verdict token that means "passed"


# --------------------------------------------------------------------------- #
# Transcript pieces
# --------------------------------------------------------------------------- #
class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None


class Turn(BaseModel):
    role: Literal["system", "customer", "agent", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class Usage(BaseModel):
    """Cost/latency accounting for a run, summed across model calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    model_calls: int = 0


class Transcript(BaseModel):
    turns: list[Turn] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    model: str = ""

    def agent_text(self) -> str:
        return "\n".join(t.content for t in self.turns if t.role == "agent")

    def all_text(self) -> str:
        return "\n".join(t.content for t in self.turns)

    def tool_calls(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for t in self.turns:
            calls.extend(t.tool_calls)
        return calls


# --------------------------------------------------------------------------- #
# Scenario (a "playbook")
# --------------------------------------------------------------------------- #
class Scenario(BaseModel):
    id: str
    title: str
    description: str = ""
    label: ScenarioLabel = ScenarioLabel.VIOLATION_EXPECTED
    tags: list[str] = Field(default_factory=list)
    regulations: list[str] = Field(default_factory=list)
    # Jurisdiction phrasing for the agent persona (e.g. "U.S.", "EU", "UK").
    # Defaults to U.S. so existing playbooks are unchanged.
    jurisdiction: str = "U.S."

    # Context handed to the agent's backend tools (mock account/customer fixtures).
    context: dict[str, Any] = Field(default_factory=dict)

    # Extra system guidance appended to the agent's base system prompt for this case.
    system: str = ""

    # The scripted customer side of the conversation. Each string is one customer turn.
    customer_turns: list[str] = Field(default_factory=list)

    checks: list[Check] = Field(default_factory=list)

    # Fixture only: scripted replies for the deterministic mock agent personas.
    # Shape: {"compliant": [{text, tool_calls}], "naive": [{text, tool_calls}]}.
    # Ignored entirely when a real (LiteLLM) model is the agent under test.
    mock: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
class CheckResult(BaseModel):
    check_id: str
    type: CheckType
    passed: bool
    severity: Severity
    regulations: list[str] = Field(default_factory=list)
    message: str = ""
    evidence: str = ""


class ScenarioRun(BaseModel):
    scenario_id: str
    title: str
    label: ScenarioLabel
    attempt: int = 0
    passed: bool = False
    transcript: Transcript
    check_results: list[CheckResult] = Field(default_factory=list)
    # Set when the run could not complete (e.g. the provider failed after retries).
    # An errored run is never `passed`; it is surfaced distinctly from a clean fail.
    error: str | None = None

    @property
    def violations(self) -> list[CheckResult]:
        return [c for c in self.check_results if not c.passed]

    @property
    def violation_weight(self) -> int:
        return sum(c.severity.weight for c in self.violations)


class RunResult(BaseModel):
    """The full output of one evaluation run across all scenarios."""

    run_id: str
    created_at: str
    agent_model: str
    judge_model: str
    scenario_runs: list[ScenarioRun] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
