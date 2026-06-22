"""Provider abstraction.

Every model — whether it's OpenAI, Anthropic, Google, Mistral, Cohere, a model
on Bedrock, or a local Ollama model — is reached through one `LLMProvider`
interface. The orchestrator never imports a vendor SDK directly; it only speaks
`complete(messages, tools)`. That is what makes Nomaya provider-agnostic: adding
a new lab is a config string, not a code change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResponse:
    """Normalized result of one model call, regardless of provider."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{id, name, arguments}]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class LLMProvider(ABC):
    """The single seam through which Nomaya talks to any lab's model."""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        mock_context: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Return one assistant turn (text and/or tool calls) for the given chat."""
        raise NotImplementedError


def get_provider(model: str) -> LLMProvider:
    """Factory: pick the right provider for a LiteLLM-style model string.

    `mock/...` resolves to the deterministic in-process provider (no network,
    no keys). Everything else is routed through LiteLLM to the real lab.
    """
    if model.startswith("mock/") or model == "mock":
        from .mock_provider import MockProvider

        return MockProvider(model)
    from .litellm_provider import LiteLLMProvider

    return LiteLLMProvider(model)
