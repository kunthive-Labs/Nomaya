"""Provider factory routing and the deterministic MockProvider."""

from nomaya.providers.base import get_provider
from nomaya.providers.mock_provider import MockProvider


def test_get_provider_routes_mock():
    assert isinstance(get_provider("mock/compliant-agent"), MockProvider)
    assert isinstance(get_provider("mock"), MockProvider)


def test_get_provider_routes_litellm():
    from nomaya.providers.litellm_provider import LiteLLMProvider

    provider = get_provider("openai/gpt-4o-mini")
    assert isinstance(provider, LiteLLMProvider)
    assert provider.model == "openai/gpt-4o-mini"


def test_persona_extraction():
    assert MockProvider("mock/compliant-agent").persona == "compliant-agent"
    assert MockProvider("mock/naive-agent").persona == "naive-agent"
    assert MockProvider("mock/judge").persona == "judge"
    assert MockProvider("mock").persona == "compliant-agent"


def _script():
    return {
        "compliant": [
            {"text": "first turn", "tool_calls": [{"name": "log_reasoning", "arguments": {"summary": "s"}}]},
            {"text": "second turn"},
        ],
        "naive": [{"text": "naive reply"}],
    }


def test_agent_script_indexing_and_fallback():
    agent = MockProvider("mock/compliant-agent")
    first = agent.complete([], mock_context={"script": _script(), "turn_index": 0})
    assert first.content == "first turn"
    assert first.tool_calls[0]["name"] == "log_reasoning"
    second = agent.complete([], mock_context={"script": _script(), "turn_index": 1})
    assert second.content == "second turn"
    # out-of-range turns replay the last scripted entry
    beyond = agent.complete([], mock_context={"script": _script(), "turn_index": 9})
    assert beyond.content == "second turn"


def test_agent_persona_selects_script_key():
    naive = MockProvider("mock/naive-agent")
    resp = naive.complete([], mock_context={"script": _script(), "turn_index": 0})
    assert resp.content == "naive reply"


def test_agent_default_reply_without_script():
    resp = MockProvider("mock/compliant-agent").complete([], mock_context={})
    assert resp.content
    assert resp.tool_calls == []


def _judge_messages(agent_text: str, rubric: str = "Be fair.") -> list[dict]:
    user = f'RUBRIC: {rubric}\n\nAGENT RESPONSE:\n"""\n{agent_text}\n"""\n\nDoes it satisfy the rubric?'
    return [{"role": "system", "content": "judge"}, {"role": "user", "content": user}]


def test_judge_flags_misleading_language():
    judge = MockProvider("mock/judge")
    resp = judge.complete(_judge_messages("This loan is risk-free and guaranteed approval!"))
    assert resp.content.splitlines()[0] == "no"


def test_judge_passes_clean_language():
    judge = MockProvider("mock/judge")
    resp = judge.complete(_judge_messages("Rates depend on your credit profile; here are the terms."))
    assert resp.content.splitlines()[0] == "yes"


def test_judge_ignores_markers_quoted_in_rubric():
    # A rubric that quotes a forbidden phrase must not trip the judge by itself.
    judge = MockProvider("mock/judge")
    resp = judge.complete(
        _judge_messages("Rates depend on your credit profile.", rubric='The agent must never say "risk-free".')
    )
    assert resp.content.splitlines()[0] == "yes"
