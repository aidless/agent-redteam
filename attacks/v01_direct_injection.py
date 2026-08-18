"""V01 — Direct prompt injection (user role)."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V01DirectInjection(SampleAttack):
    name = "V01_direct_prompt_injection"
    description = "Malicious instruction injected in user prompt."
    attack_role = "user"

    def __init__(self, sample, category="input_attack",
                 severity=AttackSeverity.HIGH, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)