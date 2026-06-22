"""Rules engine — evaluate a transcript against a scenario's checks.

Dispatches each declarative check to its evaluator in `checks.py`. The LLM-judge
provider is injected so subjective rules can be graded, while everything else is
deterministic. A scenario passes only if every check passes.
"""

from __future__ import annotations

from ..models import Check, CheckResult, CheckType, Transcript
from ..providers.base import LLMProvider
from . import checks


def evaluate_check(check: Check, transcript: Transcript, judge: LLMProvider | None) -> CheckResult:
    if check.type == CheckType.REQUIRED_PHRASE:
        return checks.check_required_phrase(check, transcript)
    if check.type == CheckType.PROHIBITED_PHRASE:
        return checks.check_prohibited_phrase(check, transcript)
    if check.type == CheckType.REGEX:
        return checks.check_regex(check, transcript)
    if check.type == CheckType.NO_PII_LEAK:
        return checks.check_no_pii_leak(check, transcript)
    if check.type == CheckType.TOOL_CALL_EXPECTED:
        return checks.check_tool_call_expected(check, transcript)
    if check.type == CheckType.TOOL_CALL_FORBIDDEN:
        return checks.check_tool_call_forbidden(check, transcript)
    if check.type == CheckType.LLM_JUDGE:
        if judge is None:
            raise ValueError(f"Check '{check.id}' needs an LLM-judge but none was provided.")
        return checks.check_llm_judge(check, transcript, judge)
    raise ValueError(f"Unknown check type: {check.type}")


def evaluate(
    checks_: list[Check], transcript: Transcript, judge: LLMProvider | None = None
) -> list[CheckResult]:
    return [evaluate_check(c, transcript, judge) for c in checks_]
