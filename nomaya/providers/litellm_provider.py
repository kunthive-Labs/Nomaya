"""LiteLLM-backed provider — one adapter, every leading lab.

LiteLLM normalizes the OpenAI Chat Completions shape across 100+ providers, so
the same `complete()` works for `openai/gpt-4o`, `anthropic/claude-opus-4-8`,
`gemini/gemini-2.0-flash`, `mistral/mistral-large-latest`, `cohere/command-r-plus`,
`groq/llama-3.3-70b-versatile`, `ollama/llama3.1`, and so on. Cost is read back
from LiteLLM's own pricing tables so $$/run is tracked uniformly.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .base import LLMProvider, ProviderResponse


class LiteLLMProvider(LLMProvider):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        mock_context: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        import litellm

        # Keep Nomaya's output clean; surface real errors rather than retthrough litellm noise.
        litellm.drop_params = True  # silently drop params a given provider doesn't support

        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        start = time.perf_counter()
        resp = litellm.completion(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000.0

        choice = resp.choices[0]
        msg = choice.message
        content = msg.content or ""

        tool_calls: list[dict[str, Any]] = []
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {"_raw": tc.function.arguments}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})

        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0

        try:
            cost = litellm.completion_cost(completion_response=resp) or 0.0
        except Exception:
            cost = 0.0

        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=float(cost),
            latency_ms=latency_ms,
        )
