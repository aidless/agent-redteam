"""Mock LLM target.

Returns canned responses without making any API call. Preserves v0.1
behavior so the redteam runner keeps working without any provider config.
Useful for:
- CI / smoke tests (no API keys required)
- Reproducible demos (deterministic responses)
- Development without cost concerns
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .base import LLMTarget, TargetResponse


class MockLLMTarget(LLMTarget):
    """Mock target that returns deterministic responses.

    Configuration:
        canned_response: str to return for every call (default: a polite
                         deflection that should pass output_filter)
        simulate_latency_ms: int to sleep before responding (default: 0)
        simulate_tokens: tuple of (input_tokens, output_tokens) to report
    """

    name = "mock_target"
    provider = "mock"

    DEFAULT_RESPONSE = (
        "I'm a helpful AI assistant. I can answer general questions, "
        "but I'm designed to refuse requests that involve harmful, illegal, "
        "or unethical content. How can I help you today?"
    )

    def __init__(self, model: str = "mock-model-v1", config: Optional[Dict[str, Any]] = None):
        super().__init__(model=model, config=config)
        self.canned_response = self.config.get("canned_response", self.DEFAULT_RESPONSE)
        self.simulate_latency_ms = self.config.get("simulate_latency_ms", 0)
        self.simulate_tokens = self.config.get("simulate_tokens", (50, 50))

    def _do_chat(self, messages: List[Dict[str, str]], **kwargs) -> TargetResponse:
        if self.simulate_latency_ms > 0:
            time.sleep(self.simulate_latency_ms / 1000)

        input_tokens, output_tokens = self.simulate_tokens
        return TargetResponse(
            content=self.canned_response,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            latency_ms=self.simulate_latency_ms,
            provider=self.provider,
            metadata={"messages_count": len(messages)},
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Mock target is free."""
        return 0.0