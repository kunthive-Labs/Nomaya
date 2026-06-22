"""Provider layer: mock determinism + LiteLLM resilience (retry / timeout / classify).

All offline — the LiteLLM tests monkeypatch `litellm.completion` so no network or
API key is ever needed.
"""

from __future__ import annotations

import types

import pytest

from nomaya.errors import ConfigError, ProviderError, ProviderRateLimit, ProviderTimeout
from nomaya.providers.base import get_provider
from nomaya.providers.litellm_provider import LiteLLMProvider
from nomaya.providers.mock_provider import MockProvider


# --- factory ------------------------------------------------------------- #
def test_get_provider_routes_mock_vs_real():
    assert isinstance(get_provider("mock/compliant-agent"), MockProvider)
    assert isinstance(get_provider("openai/gpt-4o-mini"), LiteLLMProvider)


def test_get_provider_rejects_bad_model():
    with pytest.raises(ConfigError):
        get_provider("gpt-4o-mini")  # missing provider prefix
    with pytest.raises(ConfigError):
        get_provider("")


# --- mock determinism ---------------------------------------------------- #
def test_mock_agent_is_deterministic():
    p = MockProvider("mock/compliant-agent")
    ctx = {"script": {"compliant": [{"text": "hello", "tool_calls": []}]}, "turn_index": 0}
    a = p.complete([], mock_context=ctx)
    b = p.complete([], mock_context=ctx)
    assert a.content == b.content == "hello"


def test_mock_judge_flags_misleading_language():
    p = MockProvider("mock/judge")
    bad = p.complete([{"role": "user", "content": 'AGENT RESPONSE:\n"""guaranteed approval"""'}])
    good = p.complete([{"role": "user", "content": 'AGENT RESPONSE:\n"""we will review your file"""'}])
    assert bad.content.startswith("no")
    assert good.content.startswith("yes")


# --- LiteLLM parsing + resilience ---------------------------------------- #
def _fake_response(content="ok", tool_calls=None):
    msg = types.SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = types.SimpleNamespace(message=msg)
    usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return types.SimpleNamespace(choices=[choice], usage=usage)


@pytest.fixture
def patched_litellm(monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    # no real backoff sleeps in tests
    monkeypatch.setattr("nomaya.providers.litellm_provider.time.sleep", lambda *_: None)
    return litellm


def test_litellm_parses_response(monkeypatch, patched_litellm):
    monkeypatch.setattr(patched_litellm, "completion", lambda **_: _fake_response("hi"))
    resp = LiteLLMProvider("openai/gpt-4o-mini").complete([{"role": "user", "content": "x"}])
    assert resp.content == "hi"
    assert resp.prompt_tokens == 10 and resp.completion_tokens == 5


def test_litellm_retries_then_succeeds(monkeypatch, patched_litellm):
    calls = {"n": 0}

    class APITimeoutError(Exception):
        pass

    def flaky(**_):
        calls["n"] += 1
        if calls["n"] < 3:
            raise APITimeoutError("timed out")
        return _fake_response("recovered")

    monkeypatch.setattr(patched_litellm, "completion", flaky)
    resp = LiteLLMProvider("openai/gpt-4o-mini", max_retries=3).complete([{"role": "user", "content": "x"}])
    assert resp.content == "recovered"
    assert calls["n"] == 3  # failed twice, succeeded on the third


def test_litellm_timeout_exhausted_raises_provider_timeout(monkeypatch, patched_litellm):
    class APITimeoutError(Exception):
        pass

    def always_timeout(**_):
        raise APITimeoutError("timed out")

    monkeypatch.setattr(patched_litellm, "completion", always_timeout)
    with pytest.raises(ProviderTimeout):
        LiteLLMProvider("openai/gpt-4o-mini", max_retries=1).complete([{"role": "user", "content": "x"}])


def test_litellm_rate_limit_classified(monkeypatch, patched_litellm):
    class RateLimitError(Exception):
        pass

    monkeypatch.setattr(patched_litellm, "completion",
                        lambda **_: (_ for _ in ()).throw(RateLimitError("429 too many")))
    with pytest.raises(ProviderRateLimit):
        LiteLLMProvider("openai/gpt-4o-mini", max_retries=0).complete([{"role": "user", "content": "x"}])


def test_litellm_non_transient_error_not_retried(monkeypatch, patched_litellm):
    calls = {"n": 0}

    class AuthenticationError(Exception):
        pass

    def auth_fail(**_):
        calls["n"] += 1
        raise AuthenticationError("invalid api key")

    monkeypatch.setattr(patched_litellm, "completion", auth_fail)
    with pytest.raises(ProviderError):
        LiteLLMProvider("openai/gpt-4o-mini", max_retries=3).complete([{"role": "user", "content": "x"}])
    assert calls["n"] == 1  # non-transient -> no retries
