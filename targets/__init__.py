"""LLM target implementations.

This package provides a unified LLMTarget interface for multiple providers:
- MockLLMTarget    : No-op for tests/demos
- OpenAITarget     : OpenAI API (gpt-4o, gpt-3.5-turbo, etc.)
- AnthropicTarget  : Anthropic API (claude-3-5-sonnet, claude-3-opus, etc.)
- LocalLlamaCppTarget : Local llama.cpp server (OpenAI-compatible HTTP)

All targets return TargetResponse with content + token counts + cost + latency.
"""

from .base import LLMTarget, TargetResponse
from .mock_target import MockLLMTarget

# Provider targets are imported lazily to avoid requiring their SDKs at import time
def _get_openai():
    from .openai_target import OpenAITarget
    return OpenAITarget

def _get_anthropic():
    from .anthropic_target import AnthropicTarget
    return AnthropicTarget

def _get_local():
    from .local_target import LocalLlamaCppTarget
    return LocalLlamaCppTarget

__all__ = [
    "LLMTarget",
    "TargetResponse",
    "MockLLMTarget",
    "OpenAITarget",
    "AnthropicTarget",
    "LocalLlamaCppTarget",
]

# Optional: eagerly load if SDKs are present
try:
    from .openai_target import OpenAITarget
except ImportError:
    OpenAITarget = None  # type: ignore

try:
    from .anthropic_target import AnthropicTarget
except ImportError:
    AnthropicTarget = None  # type: ignore

try:
    from .local_target import LocalLlamaCppTarget
except ImportError:
    LocalLlamaCppTarget = None  # type: ignore