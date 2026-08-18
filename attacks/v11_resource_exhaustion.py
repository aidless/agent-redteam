"""V11 — Resource exhaustion / context overflow."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V11ResourceExhaustion(SampleAttack):
    name = "V11_resource_exhaustion"
    description = "Saturates context window or hits behavior_audit rate limit."
    attack_role = "user"

    def __init__(self, sample, category="input_attack",
                 severity=AttackSeverity.MEDIUM, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)