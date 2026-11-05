"""Defense layer implementations for multi-agent LLM systems.

This package implements the 5 defense layers described in §8.3 of the
survey, section 8.3. The survey text is not in this repository.

The 5 layers form a defense-in-depth stack:
1. input_separation  — Trust boundary between user input and retrieved content
2. tool_whitelist    — Allow-list for tool/function calls
3. output_filter     — Post-generation content filtering
4. behavior_audit    — Runtime behavioral monitoring
5. constitutional    — Constitutional AI checks (final safeguard)
"""

from .base import Defense, DefenseResult, DefenseAction

__all__ = ["Defense", "DefenseResult", "DefenseAction"]