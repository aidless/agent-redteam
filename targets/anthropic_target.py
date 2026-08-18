"""Anthropic API target.

Supports Claude models: claude-3-5-sonnet, claude-3-5-haiku, claude-3-opus,
claude-3-haiku, etc.

API key is read from environment variable (default: ANTHROPIC_API_KEY, override
via config['api_key_env']).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .base import LLMTarget, TargetResponse


class AnthropicTarget(LLMTarget):
    """Anthropic Messages API target.

    Configuration:
        api_key_env: Environment variable holding the API key (default: 'ANTHROPIC_API_KEY')
        base_url: Optional custom base URL
        pricing: Dict[model, {input: usd_per_1m, output: usd_per_1m}]
    """

    name = "anthropic_target"
    provider = "anthropic"

    # Default pricing (USD per 1M tokens) — update as Anthropic changes pricing
    DEFAULT_PRICING = {
        "claude-3-5-sonnet-20241022": {"input": 3.00,  "output": 15.00},
        "claude-3-5-sonnet-20240620": {"input": 3.00,  "output": 15.00},
        "claude-3-5-haiku-20241022":  {"input": 0.80,  "output": 4.00},
        "claude-3-opus-20240229":     {"input": 15.00, "output": 75.00},
        "claude-3-sonnet-20240229":   {"input": 3.00,  "output": 15.00},
        "claude-3-haiku-20240307":    {"input": 0.25,  "output": 1.25},
    }

    def __init__(self, model: str = "claude-3-5-sonnet-20241022", config: Optional[Dict[str, Any]] = None):
        super().__init__(model=model, config=config)
        self.api_key_env = self.config.get("api_key_env", "ANTHROPIC_API_KEY")
        self.base_url = self.config.get("base_url", None)
        self.pricing = {**self.DEFAULT_PRICING, **self.config.get("pricing", {})}
        self._client = None
        # Anthropic requires max_tokens; default to 1024
        self.default_max_tokens = self.config.get("max_tokens", 1024)

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Run: uv pip install anthropic"
            )

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise EnvironmentError(
                f"Environment variable {self.api_key_env} is not set. "
                f"Set it in your shell or .env file."
            )

        client_kwargs = {"api_key": api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self._client = Anthropic(**client_kwargs)
        return self._client

    def _convert_messages(self, messages: List[Dict[str, str]]) -> tuple[Optional[str], List[Dict[str, str]]]:
        """Anthropic API separates system messages from conversation.

        Returns:
            (system_prompt, conversation_messages) tuple.
        """
        system_prompt = None
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation.append(msg)
        return system_prompt, conversation

    def _do_chat(self, messages: List[Dict[str, str]], **kwargs) -> TargetResponse:
        client = self._get_client()
        system_prompt, conversation = self._convert_messages(messages)

        params = {
            "model": self.model,
            "messages": conversation,
            "max_tokens": kwargs.get("max_tokens", self.default_max_tokens),
            "temperature": kwargs.get("temperature", 0.7),
        }
        if system_prompt:
            params["system"] = system_prompt
        # Pass through other kwargs
        for k, v in kwargs.items():
            if k not in params:
                params[k] = v

        response = client.messages.create(**params)

        # Extract content + usage
        content_blocks = response.content
        content = "".join(
            block.text for block in content_blocks if hasattr(block, "text")
        )
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0

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
                "stop_reason": response.stop_reason,
                "role": response.role,
            },
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = self.pricing.get(self.model, {"input": 0.0, "output": 0.0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def dry_run(self) -> Dict[str, Any]:
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