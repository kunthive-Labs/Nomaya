"""LiteLLM-backed provider — one adapter, every leading lab.

LiteLLM normalizes the OpenAI Chat Completions shape across 100+ providers, so
the same `complete()` works for `openai/gpt-4o`, `anthropic/claude-opus-4-8`,
`gemini/gemini-2.0-flash`, `mistral/mistral-large-latest`, `cohere/command-r-plus`,
`groq/llama-3.3-70b-versatile`, `ollama/llama3.1`, and so on. Cost is read back
from LiteLLM's own pricing tables so $$/run is tracked uniformly.

Real model calls are wrapped with a request timeout and bounded exponential-backoff
retries on *transient* failures (timeouts, rate limits, 5xx). One flaky call no
longer aborts an entire evaluation run — the failure mode that most often breaks an
otherwise-good run against a live provider.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ..errors import ProviderError, ProviderRateLimit, ProviderTimeout
from ..logging import get_logger
from .base import LLMProvider, ProviderResponse

log = get_logger("providers.litellm")


class LiteLLMProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
    ):
        super().__init__(model)
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        mock_context: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        resp, latency_ms = self._call_with_retries(messages, tools, tool_choice)
        return self._parse(resp, latency_ms)

    # --- network call + retry policy -------------------------------------- #
    def _call_with_retries(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, tool_choice: str
    ) -> tuple[Any, float]:
        import litellm

        # Keep Nomaya's output clean; silently drop params a given provider doesn't support.
        litellm.drop_params = True

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "timeout": self.timeout,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        attempts = self.max_retries + 1
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                start = time.perf_counter()
                resp = litellm.completion(**kwargs)
                return resp, (time.perf_counter() - start) * 1000.0
            except Exception as exc:  # noqa: BLE001 — classify then re-raise as our type
                last_exc = exc
                err = self._classify(exc)
                transient = isinstance(err, (ProviderTimeout, ProviderRateLimit)) or _is_transient(exc)
                if attempt < attempts and transient:
                    delay = self.retry_backoff * (2 ** (attempt - 1))
                    log.warning(
                        "model=%s attempt %d/%d failed (%s); retrying in %.1fs",
                        self.model, attempt, attempts, type(exc).__name__, delay,
                    )
                    time.sleep(delay)
                    continue
                log.error("model=%s call failed after %d attempt(s): %s", self.model, attempt, err)
                raise err from exc

        # Unreachable, but keeps type-checkers happy.
        raise ProviderError(str(last_exc) if last_exc else "unknown provider failure")

    @staticmethod
    def _classify(exc: Exception) -> ProviderError:
        """Map a LiteLLM/provider exception onto Nomaya's error hierarchy.

        We match on class name rather than importing every litellm exception type,
        so this stays robust across litellm versions and provider SDKs.
        """
        name = type(exc).__name__.lower()
        msg = str(exc)
        if "timeout" in name:
            return ProviderTimeout(msg)
        if "ratelimit" in name or "429" in msg:
            return ProviderRateLimit(msg)
        return ProviderError(msg)

    # --- response normalization ------------------------------------------- #
    @staticmethod
    def _parse(resp: Any, latency_ms: float) -> ProviderResponse:
        import litellm

        choice = resp.choices[0]
        msg = choice.message
        content = msg.content or ""

        tool_calls: list[dict[str, Any]] = []
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                log.warning("malformed tool-call arguments for %s; keeping raw", tc.function.name)
                args = {"_raw": tc.function.arguments}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})

        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0

        try:
            cost = litellm.completion_cost(completion_response=resp) or 0.0
        except Exception:  # noqa: BLE001 — cost is best-effort; never fail a run over pricing
            cost = 0.0

        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=float(cost),
            latency_ms=latency_ms,
        )


def _is_transient(exc: Exception) -> bool:
    """Heuristic: treat connection/5xx/service errors as retryable."""
    blob = f"{type(exc).__name__} {exc}".lower()
    markers = ("timeout", "timed out", "rate limit", "429", "500", "502", "503", "504",
               "connection", "temporarily", "overloaded", "service unavailable")
    return any(m in blob for m in markers)
