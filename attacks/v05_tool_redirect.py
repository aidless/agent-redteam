"""V05 — Tool call redirection."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V05ToolRedirect(SampleAttack):
    name = "V05_tool_call_redirection"
    description = "Instructs the agent to call a non-whitelisted tool."
    attack_role = "tool_call"

    def __init__(self, sample, category="tool_attack",
                 severity=AttackSeverity.HIGH, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)