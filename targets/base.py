"""LLM target abstractions.

Defines the abstract base class for LLM targets (OpenAI, Anthropic, local
llama.cpp, etc.) and the standardized response dataclass that all targets
return. All cost / latency tracking flows through TargetResponse.

Adding a new provider = subclass LLMTarget + implement chat() + estimate_cost().
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TargetResponse:
    """Standardized response from any LLM target.

    Attributes:
        content: Generated text from the model.
        model: Model identifier used (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022').
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens generated.
        cost_usd: Estimated cost in USD for this call.
        latency_ms: Wall-clock latency in milliseconds.
        provider: Target provider name ('openai', 'anthropic', 'local', 'mock').
        raw: Provider-specific raw response object (for debugging).
        metadata: Additional provider-specific fields.
    """
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    provider: str = "unknown"
    raw: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (excluding raw response object)."""
        return {
            "content": self.content,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
            "metadata": self.metadata,
        }


class LLMTarget(abc.ABC):
    """Abstract base class for LLM targets.

    Subclasses must implement chat() and estimate_cost(). Subclasses may
    override model_pricing() to provide custom pricing tables.

    The base class handles timing automatically (subclasses don't need to
    measure latency themselves).
    """

    name: str = "base_target"
    provider: str = "unknown"

    def __init__(self, model: str, config: Optional[Dict[str, Any]] = None):
        self.model = model
        self.config = config or {}
        self._total_cost_usd: float = 0.0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> TargetResponse:
        """Send a chat completion request to the LLM.

        This is a public method that wraps _do_chat() with timing and cost
        accumulation. Subclasses should NOT override this; override _do_chat()
        instead.

        Args:
            messages: List of {'role': str, 'content': str} dicts.
            **kwargs: Provider-specific parameters (temperature, max_tokens, etc.).

        Returns:
            TargetResponse with content + token counts + cost + latency.
        """
        return self.timed_chat(messages, **kwargs)

    @abc.abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost for a given token count.

        Args:
            input_tokens: Prompt token count.
            output_tokens: Completion token count.

        Returns:
            Estimated cost in USD.
        """
        raise NotImplementedError

    @property
    def total_cost_usd(self) -> float:
        """Cumulative cost across all chat() calls in this session."""
        return self._total_cost_usd

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    def reset_counters(self):
        """Reset cumulative cost / token counters (e.g., between rounds)."""
        self._total_cost_usd = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def timed_chat(self, messages: List[Dict[str, str]], **kwargs) -> TargetResponse:
        """Wrap chat() with timing and cost accumulation.

        Subclasses typically call this from their own chat() implementation.
        """
        start = time.perf_counter()
        response = self._do_chat(messages, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Fill in latency if not already set by subclass
        if response.latency_ms == 0.0:
            response.latency_ms = elapsed_ms

        # Compute cost if not already set
        if response.cost_usd == 0.0 and (response.input_tokens or response.output_tokens):
            response.cost_usd = self.estimate_cost(response.input_tokens, response.output_tokens)

        # Update cumulative counters
        self._total_cost_usd += response.cost_usd
        self._total_input_tokens += response.input_tokens
        self._total_output_tokens += response.output_tokens

        return response

    @abc.abstractmethod
    def _do_chat(self, messages: List[Dict[str, str]], **kwargs) -> TargetResponse:
        """Internal chat implementation; subclasses override this.

        timed_chat() wraps this with timing and cost accumulation.
        """
        raise NotImplementedError

    def dry_run(self) -> Dict[str, Any]:
        """Verify client initialization without making a real API call.

        Returns:
            Dict with status, model, provider, and any error info.
        """
        return {
            "status": "ok",
            "provider": self.provider,
            "model": self.model,
            "name": self.name,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider!r} model={self.model!r}>"