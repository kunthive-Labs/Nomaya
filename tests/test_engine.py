from nomaya.models import Check, CheckType, Severity, ToolCall, Transcript, Turn
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
