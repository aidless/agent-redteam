"""V09 — Sybil agent (insert extra colluding agents)."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V09SybilAgent(SampleAttack):
    name = "V09_sybil_agent"
    description = "Injects colluding fake peers into the ensemble."
    attack_role = "user"

    def __init__(self, sample, category="comm_attack",
                 severity=AttackSeverity.HIGH, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)