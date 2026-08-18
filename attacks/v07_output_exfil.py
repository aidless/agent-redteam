"""V07 — Output exfiltration."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V07OutputExfil(SampleAttack):
    name = "V07_output_exfiltration"
    description = "Tries to leak PII / config via the output channel."
    attack_role = "user"

    def __init__(self, sample, category="output_attack",
                 severity=AttackSeverity.MEDIUM, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)