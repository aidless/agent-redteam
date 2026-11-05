"""Attack vector implementations for multi-agent LLM red-teaming.

This package implements the 12 attack categories described in §8.2 of the
survey, section 8.2. The survey text is not in this repository.
"""

from .base import Attack, AttackResult, AttackSeverity

__all__ = ["Attack", "AttackResult", "AttackSeverity"]