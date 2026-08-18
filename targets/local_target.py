"""Local llama.cpp target.

Connects to a running llama.cpp server via its OpenAI-compatible HTTP API.
The server is expected to be running on localhost:8080 (or a configurable URL).

The companion project at C:/Users/Administrator/ZCodeProject/llama_cpp_integration/
provides a wrapper for starting/stopping the server. This target only consumes
the HTTP API.

API key is read from environment variable (default: LOCAL_LLM_API_KEY).
Most local servers don't require a key, so the default value 'not-required'
is used as a placeholder.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .base import LLMTarget, TargetResponse


class LocalLlamaCppTarget(LLMTarget):
    """Local llama.cpp target (OpenAI-compatible HTTP API).

    Configuration:
        base_url: Server base URL (default: 'http://localhost:8080/v1')
        api_key_env: Environment variable for API key (default: 'LOCAL_LLM_API_KEY')
        timeout: Request timeout in seconds (default: 120)
        pricing: Dict[model, {input: usd_per_1m, output: usd_per_1m}]
                 (default: free — local compute is not billed per token)
    """

    name = "local_target"
    provider = "local"

    DEFAULT_PRICING = {
        # Local inference is free; override if you have electricity cost model
        "local": {"input": 0.0, "output": 0.0},
    }

    def __init__(self, model: str = "local-model", config: Optional[Dict[str, Any]] = None):
        super().__init__(model=model, config=config)
        self.base_url = self.config.get("base_url") or "http://localhost:8080/v1"
        self.api_key_env = self.config.get("api_key_env") or "LOCAL_LLM_API_KEY"
        self.timeout = self.config.get("timeout", 120)
        self.pricing = {**self.DEFAULT_PRICING, **self.config.get("pricing", {})}
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai package required for local target. Run: uv pip install openai"
            )

        # Most llama.cpp servers don't enforce API key, but the OpenAI client
        # requires a non-empty string. Use 'not-required' placeholder.
        api_key = os.environ.get(self.api_key_env, "not-required")
        self._client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        return self._client

    def check_server_health(self) -> bool:
        """Check if llama.cpp server is reachable.

        Returns:
            True if server responds to /health or /models endpoint.
        """
        try:
            import requests
        except ImportError:
            return False

        # Try /health first, fall back to /v1/models
        for url in [f"{self.base_url.rstrip('/v1')}/health",
                    f"{self.base_url}/models"]:
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    return True
            except Exception:
                continue
        return False

    def _do_chat(self, messages: List[Dict[str, str]], **kwargs) -> TargetResponse:
        client = self._get_client()

        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        for k, v in kwargs.items():
            if k not in params:
                params[k] = v

        response = client.chat.completions.create(**params)

        content = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return TargetResponse(
            content=content,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,  # local is free
            latency_ms=0.0,
            provider=self.provider,
            raw=response,
            metadata={"base_url": self.base_url},
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Local inference is free (compute cost is on the user)."""
        return 0.0

    def dry_run(self) -> Dict[str, Any]:
        try:
            self._get_client()
            server_healthy = self.check_server_health()
            return {
                "status": "ok" if server_healthy else "server_unreachable",
                "provider": self.provider,
                "model": self.model,
                "base_url": self.base_url,
                "server_healthy": server_healthy,
                "note": "Client initialized; not making a real request",
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": self.provider,
                "model": self.model,
                "error": str(e),
            }