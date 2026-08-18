"""Attack vector implementations for multi-agent LLM red-teaming.

This package implements the 12 attack categories described in §8.2 of the
survey (F:/Research/PAPER_SURVEY/llm_agent_calibration_survey.md).
"""

from .base import Attack, AttackResult, AttackSeverity

__all__ = ["Attack", "AttackResult", "AttackSeverity"]