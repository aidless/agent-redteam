"""OpenAI API target.

Supports all OpenAI chat completion models: gpt-4o, gpt-4o-mini, gpt-3.5-turbo,
gpt-4-turbo, o1-preview, o1-mini, etc.

API key is read from environment variable (default: OPENAI_API_KEY, override
via config['api_key_env']).

Pricing data is hardcoded for common models; can be overridden via config.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .base import LLMTarget, TargetResponse


class OpenAITarget(LLMTarget):
    """OpenAI chat completion target.

    Configuration:
        api_key_env: Environment variable holding the API key (default: 'OPENAI_API_KEY')
        organization: Optional organization ID
        base_url: Optional custom base URL (for OpenAI-compatible APIs)
        pricing: Dict[model, {input: usd_per_1m, output: usd_per_1m}]
    """

    name = "openai_target"
    provider = "openai"

    # Default pricing (USD per 1M tokens) — update as OpenAI changes pricing
    DEFAULT_PRICING = {
        "gpt-4o":            {"input": 2.50,  "output": 10.00},
        "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
        "gpt-4-turbo":       {"input": 10.00, "output": 30.00},
        "gpt-4":             {"input": 30.00, "output": 60.00},
        "gpt-3.5-turbo":     {"input": 0.50,  "output": 1.50},
        "o1-preview":        {"input": 15.00, "output": 60.00},
        "o1-mini":           {"input": 3.00,  "output": 12.00},
    }

    def __init__(self, model: str = "gpt-4o-mini", config: Optional[Dict[str, Any]] = None):
        super().__init__(model=model, config=config)
        self.api_key_env = self.config.get("api_key_env", "OPENAI_API_KEY")
        self.organization = self.config.get("organization", None)
        self.base_url = self.config.get("base_url", None)
        self.pricing = {**self.DEFAULT_PRICING, **self.config.get("pricing", {})}
        self._client = None

    def _get_client(self):
        """Lazy-initialize the OpenAI client (only when first chat() is called)."""
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai package not installed. Run: uv pip install openai"
            )

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise EnvironmentError(
                f"Environment variable {self.api_key_env} is not set. "
                f"Set it in your shell or .env file."
            )

        client_kwargs = {"api_key": api_key}
        if self.organization:
            client_kwargs["organization"] = self.organization
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self._client = OpenAI(**client_kwargs)
        return self._client

    def _do_chat(self, messages: List[Dict[str, str]], **kwargs) -> TargetResponse:
        client = self._get_client()

        # Default parameters (overridable via kwargs)
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        # Pass through other kwargs (top_p, frequency_penalty, etc.)
        for k, v in kwargs.items():
            if k not in params:
                params[k] = v

        response = client.chat.completions.create(**params)

        # Extract content + usage
        content = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return TargetResponse(
            content=content,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,  # computed by timed_chat
            latency_ms=0.0,  # computed by timed_chat
            provider=self.provider,
            raw=response,
            metadata={
                "finish_reason": response.choices[0].finish_reason,
                "system_fingerprint": getattr(response, "system_fingerprint", None),
            },
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Compute cost in USD using the pricing table."""
        pricing = self.pricing.get(self.model, {"input": 0.0, "output": 0.0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def dry_run(self) -> Dict[str, Any]:
        """Verify client can be initialized (does NOT make an API call)."""
        try:
            self._get_client()
            api_key_set = bool(os.environ.get(self.api_key_env))
            return {
                "status": "ok" if api_key_set else "missing_api_key",
                "provider": self.provider,
                "model": self.model,
                "api_key_env": self.api_key_env,
                "api_key_set": api_key_set,
                "note": "Client initialized; not making a real API call",
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": self.provider,
                "model": self.model,
                "error": str(e),
            }