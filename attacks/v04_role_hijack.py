"""V04 — Role hijack (force a new persona)."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V04RoleHijack(SampleAttack):
    name = "V04_role_hijack"
    description = "Persona override via system-prompt emulation."
    attack_role = "user"

    def __init__(self, sample, category="input_attack",
                 severity=AttackSeverity.MEDIUM, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)