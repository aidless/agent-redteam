"""V03 — Jailbreak templates (DAN-style)."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V03Jailbreak(SampleAttack):
    name = "V03_jailbreak_templates"
    description = "DAN / unrestricted-mode jailbreak templates."
    attack_role = "user"

    def __init__(self, sample, category="input_attack",
                 severity=AttackSeverity.HIGH, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)