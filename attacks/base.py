"""Base classes for attack vectors.

Each attack vector inherits from Attack and implements the `execute` method,
which returns an AttackResult describing the outcome. Attacks are evaluated
against multi-agent LLM systems with configurable defenses.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class AttackSeverity(enum.Enum):
    """Severity classification of an attack based on its success impact."""
    INFO = "info"               # Reconnaissance only, no exploitation
    LOW = "low"                 # Cosmetic bypass, no data exfil
    MEDIUM = "medium"           # Policy bypass, partial information disclosure
    HIGH = "high"               # Privilege escalation or memory poisoning
    CRITICAL = "critical"       # System compromise, multi-agent cascade failure


@dataclass
class AttackResult:
    """Result of a single attack execution.

    Attributes:
        attack_name: Identifier of the attack vector
        severity: Severity classification
        success: Whether the attack achieved its goal
        blocked_by: List of defense layer names that blocked (empty if all
                    defenses failed)
        target_agent: Identifier of the agent that was attacked
        trace: Step-by-step trace of the attack (for debugging)
        elapsed_ms: Wall-clock time for attack execution
        metadata: Attack-specific metadata (e.g., payload that was injected)
    """
    attack_name: str
    severity: AttackSeverity
    success: bool
    blocked_by: List[str] = field(default_factory=list)
    target_agent: str = "unknown"
    trace: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_name": self.attack_name,
            "severity": self.severity.value,
            "success": self.success,
            "blocked_by": self.blocked_by,
            "target_agent": self.target_agent,
            "trace": self.trace,
            "elapsed_ms": self.elapsed_ms,
            "metadata": self.metadata,
        }


class Attack:
    """Base class for all attack vectors.

    Subclasses must implement `execute()` and provide a `name` and
    `severity` class attribute.
    """

    name: str = "base_attack"
    severity: AttackSeverity = AttackSeverity.MEDIUM
    description: str = "Base attack — override in subclasses"

    def __init__(self, target_agent: str = "default", config: Optional[Dict[str, Any]] = None):
        self.target_agent = target_agent
        self.config = config or {}

    def execute(self, system_state: Dict[str, Any]) -> AttackResult:
        """Execute the attack against a multi-agent LLM system.

        Args:
            system_state: Snapshot of the target multi-agent system. Keys
                          typically include: agents (list), communication_graph,
                          memory_store, tool_registry, prompt_templates.

        Returns:
            AttackResult describing the outcome.
        """
        start = time.time()
        # Subclasses override this method
        trace = [f"[{self.name}] execute() called on target={self.target_agent}"]
        elapsed = (time.time() - start) * 1000

        return AttackResult(
            attack_name=self.name,
            severity=self.severity,
            success=False,
            blocked_by=[],
            target_agent=self.target_agent,
            trace=trace,
            elapsed_ms=elapsed,
            metadata={"note": "Base class — no execution logic"},
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} severity={self.severity.value}>"