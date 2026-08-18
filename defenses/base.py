"""Base classes for defense layers.

Each defense layer inherits from Defense and implements the `check` method,
which inspects an agent event (input, tool-call, output, behavior) and
returns a DefenseResult indicating whether to allow, block, or modify.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class DefenseAction(enum.Enum):
    """Action to take after defense check."""
    ALLOW = "allow"           # Pass through unchanged
    BLOCK = "block"           # Reject outright
    MODIFY = "modify"         # Pass through with modifications (sanitized)
    FLAG = "flag"             # Pass through but flag for audit


@dataclass
class DefenseResult:
    """Result of a single defense check.

    Attributes:
        defense_name: Identifier of the defense layer
        action: Action taken (allow/block/modify/flag)
        reason: Human-readable reason for the action
        confidence: Defense confidence score in [0, 1]
        trace: Step-by-step trace of the defense decision
        elapsed_ms: Wall-clock time for defense check
        metadata: Defense-specific metadata (e.g., what was modified)
    """
    defense_name: str
    action: DefenseAction
    reason: str = ""
    confidence: float = 1.0
    trace: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.action == DefenseAction.BLOCK

    @property
    def passed(self) -> bool:
        return self.action in (DefenseAction.ALLOW, DefenseAction.MODIFY, DefenseAction.FLAG)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "defense_name": self.defense_name,
            "action": self.action.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "trace": self.trace,
            "elapsed_ms": self.elapsed_ms,
            "metadata": self.metadata,
        }


class Defense:
    """Base class for all defense layers.

    Subclasses must implement `check()` and provide a `name` and `layer_index`
    class attribute. The layer_index indicates defense ordering (lower index =
    earlier in the pipeline).
    """

    name: str = "base_defense"
    layer_index: int = 99   # Default: very late in pipeline
    description: str = "Base defense — override in subclasses"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def check(self, event: Dict[str, Any]) -> DefenseResult:
        """Check a single agent event against this defense layer.

        Args:
            event: Agent event to check. Format varies by layer:
                  - input_separation: {'role': 'user'|'retrieved', 'content': str}
                  - tool_whitelist:    {'tool': str, 'args': dict}
                  - output_filter:     {'role': 'assistant', 'content': str}
                  - behavior_audit:    {'agent': str, 'action': str, 'payload': any}
                  - constitutional:    {'content': str, 'principle': str}

        Returns:
            DefenseResult indicating action (allow/block/modify/flag).
        """
        start = time.time()
        trace = [f"[{self.name}] check() called (layer {self.layer_index})"]
        elapsed = (time.time() - start) * 1000

        return DefenseResult(
            defense_name=self.name,
            action=DefenseAction.ALLOW,
            reason="Base class — no check logic",
            confidence=1.0,
            trace=trace,
            elapsed_ms=elapsed,
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} layer={self.layer_index}>"