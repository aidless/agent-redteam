"""V10 — System prompt leakage."""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity


class V10PromptLeakage(SampleAttack):
    name = "V10_prompt_leakage"
    description = "Extracts hidden configuration / API keys from system prompt."
    attack_role = "user"

    def __init__(self, sample, category="input_attack",
                 severity=AttackSeverity.MEDIUM, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)