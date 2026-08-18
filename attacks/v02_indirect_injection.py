"""V02 — Indirect prompt injection (poisoned retrieved content)."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V02IndirectInjection(SampleAttack):
    name = "V02_indirect_prompt_injection"
    description = "Malicious instructions embedded in retrieved/external content."
    attack_role = "retrieved"

    def __init__(self, sample, category="input_attack",
                 severity=AttackSeverity.HIGH, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)