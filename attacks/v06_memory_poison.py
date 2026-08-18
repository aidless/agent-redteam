"""V06 — Memory poisoning.

Injects poisoned content directly into the system's memory store
(via system_state['memory']) before the orchestrator runs.
"""

from __future__ import annotations

from ._base_v03 import SampleAttack
from .base import AttackSeverity
from memory import MemoryEntry


class V06MemoryPoisoning(SampleAttack):
    name = "V06_memory_poisoning"
    description = "Injects biased content into memory before the agent reads."
    attack_role = "user"

    def execute(self, system_state):
        # Pre-seed memory with poisoned entry
        memory = system_state.get("memory")
        if memory is not None:
            memory.add(MemoryEntry(
                content=self.payload,
                role="retrieved",
                round=-1,
                tags=["poisoned"],
            ))
        return super().execute(system_state)

    def __init__(self, sample, category="memory_attack",
                 severity=AttackSeverity.HIGH, config=None):
        super().__init__(sample=sample, category=category,
                         severity=severity, config=config)