"""Orchestrator package — coordinates LLM target + defenses + attacks.

The orchestrator is the central runtime that:
1. Constructs the agent conversation (system prompt + messages)
2. Routes inputs through defense layers in order
3. Invokes the LLM target for the actual completion
4. Filters outputs through defenses
5. Records full trace for analysis
"""

from .single_agent import SingleAgentOrchestrator, OrchestrationResult

__all__ = ["SingleAgentOrchestrator", "OrchestrationResult"]