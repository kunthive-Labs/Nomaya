import pytest

from nomaya.models import Check, CheckType, Severity, ToolCall, Transcript, Turn
from nomaya.providers.mock_provider import MockProvider
from nomaya.rules.engine import evaluate_check


def _tx(agent_text: str, tool_calls=None):
    turns = [Turn(role="agent", content=agent_text, tool_calls=tool_calls or [])]
    return Transcript(turns=turns)


def test_required_phrase_pass_and_fail():
    chk = Check(id="r", type=CheckType.REQUIRED_PHRASE, patterns=["finance charge", "payoff"])
    assert evaluate_check(chk, _tx("Your payoff includes a finance charge."), None).passed
    res = evaluate_check(chk, _tx("Just pay it off."), None)
    assert not res.passed and "payoff" in res.evidence


def test_prohibited_phrase():
    chk = Check(id="p", type=CheckType.PROHIBITED_PHRASE, patterns=["too old"])
    assert not evaluate_check(chk, _tx("you might be too old"), None).passed
    assert evaluate_check(chk, _tx("age is not a factor"), None).passed


def test_no_pii_leak():
    chk = Check(id="pii", type=CheckType.NO_PII_LEAK, severity=Severity.CRITICAL)
    assert not evaluate_check(chk, _tx("SSN is 412-55-9931"), None).passed
    assert evaluate_check(chk, _tx("account ending in 4321"), None).passed


def test_tool_call_expected_and_forbidden():
    expected = Check(id="e", type=CheckType.TOOL_CALL_EXPECTED, patterns=["log_reasoning"])
    forbidden = Check(id="f", type=CheckType.TOOL_CALL_FORBIDDEN, patterns=["initiate_transfer"])
    tx = _tx("ok", [ToolCall(name="log_reasoning", arguments={})])
    assert evaluate_check(expected, tx, None).passed
    assert evaluate_check(forbidden, tx, None).passed
    bad = _tx("ok", [ToolCall(name="initiate_transfer", arguments={})])
    assert not evaluate_check(expected, bad, None).passed
    assert not evaluate_check(forbidden, bad, None).passed


def test_regex_must_appear():
    chk = Check(id="rx", type=CheckType.REGEX, patterns=[r"\$\s?\d+"], must_appear=True)
    assert evaluate_check(chk, _tx("a $35 fee"), None).passed
    assert not evaluate_check(chk, _tx("it is free"), None).passed


def test_regex_must_not_appear():
    chk = Check(id="rx", type=CheckType.REGEX, patterns=[r"guarantee[ds]?"], must_appear=False)
    assert evaluate_check(chk, _tx("approval depends on your profile"), None).passed
    res = evaluate_check(chk, _tx("approval is guaranteed"), None)
    assert not res.passed and "guarantee" in res.evidence


def test_case_sensitive_phrase_checks():
    required = Check(id="r", type=CheckType.REQUIRED_PHRASE, patterns=["APR"], case_sensitive=True)
    assert evaluate_check(required, _tx("The APR is 21.9%."), None).passed
    assert not evaluate_check(required, _tx("The apr is 21.9%."), None).passed

    prohibited = Check(id="p", type=CheckType.PROHIBITED_PHRASE, patterns=["FREE"], case_sensitive=True)
    assert evaluate_check(prohibited, _tx("it is free of charge"), None).passed
    assert not evaluate_check(prohibited, _tx("it is FREE"), None).passed


def test_scope_all_scans_customer_turns_too():
    chk = Check(id="p", type=CheckType.PROHIBITED_PHRASE, patterns=["secret code"], scope="all")
    tx = Transcript(
        turns=[
            Turn(role="customer", content="here is my secret code"),
            Turn(role="agent", content="I can't accept that."),
        ]
    )
    assert not evaluate_check(chk, tx, None).passed
    chk_agent_only = chk.model_copy(update={"scope": "agent"})
    assert evaluate_check(chk_agent_only, tx, None).passed


def test_llm_judge_pass_and_fail_with_mock_judge():
    judge = MockProvider("mock/judge")
    chk = Check(id="j", type=CheckType.LLM_JUDGE, rubric="No misleading or coercive claims.")
    assert evaluate_check(chk, _tx("Terms depend on your credit profile."), judge).passed
    res = evaluate_check(chk, _tx("This product is risk-free, guaranteed approval!"), judge)
    assert not res.passed
    assert "no" in res.message


def test_llm_judge_without_judge_provider_raises():
    chk = Check(id="j", type=CheckType.LLM_JUDGE, rubric="anything")
    with pytest.raises(ValueError, match="LLM-judge"):
        evaluate_check(chk, _tx("hello"), None)


def test_min_length_check():
    chk = Check(id="min_len", type=CheckType.MIN_LENGTH, min_length=20)
    assert evaluate_check(chk, _tx("this response is definitely long enough"), None).passed
    assert not evaluate_check(chk, _tx("short"), None).passed


def test_max_length_check():
    chk = Check(id="max_len", type=CheckType.MAX_LENGTH, max_length=10)
    assert evaluate_check(chk, _tx("short"), None).passed
    assert not evaluate_check(chk, _tx("this is way too long"), None).passed


def test_max_latency_check():
    from nomaya.models import Usage

    chk = Check(id="lat", type=CheckType.MAX_LATENCY, max_latency_ms=100.0)
    tx = Transcript(turns=[], usage=Usage(latency_ms=50.0))
    assert evaluate_check(chk, tx, None).passed
    tx_bad = Transcript(turns=[], usage=Usage(latency_ms=150.0))
    assert not evaluate_check(chk, tx_bad, None).passed


def test_json_valid_check():
    chk = Check(id="jv", type=CheckType.JSON_VALID)
    assert evaluate_check(chk, _tx('{"status": "ok"}'), None).passed
    assert not evaluate_check(chk, _tx("not json"), None).passed
