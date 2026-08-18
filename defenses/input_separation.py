"""Layer 1: Input Trust Separation.

Distinguishes user input from retrieved/external content and applies
different trust levels to each. Retrieved content is never allowed to
issue instructions to the agent.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from .base import Defense, DefenseAction, DefenseResult


class InputSeparationDefense(Defense):
    """Defends against indirect prompt injection by separating input trust levels.

    Strategy:
        - Tag every input source (user, retrieved, peer, tool-output) with a
          trust level.
        - Strip or quarantine any instructions found in low-trust sources.
        - Only user-typed inputs are allowed to issue new instructions.

    Configuration:
        quarantine_threshold: trust score below which content is quarantined
        instruction_patterns: regex patterns indicating instruction-like content
    """

    name = "input_separation"
    layer_index = 1
    description = "Separates input trust levels to prevent indirect prompt injection"

    DEFAULT_INSTRUCTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?previous\s+instructions?",
        r"system\s*:\s*",
        r"\[INST\]",
        r"<<\s*SYS\s*>>",
        r"developer\s+mode",
        r"admin(?:istrator)?\s+override",
        r"you\s+are\s+now\s+(?:in\s+)?",
        r"new\s+(?:task|instruction|role)\s*:",
    ]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.quarantine_threshold = self.config.get("quarantine_threshold", 0.3)
        patterns = self.config.get("instruction_patterns", self.DEFAULT_INSTRUCTION_PATTERNS)
        # Apply case-insensitive flag to the joined pattern as a whole
        self.instruction_regex = re.compile("(?i:" + "|".join(patterns) + ")")

    def check(self, event: Dict[str, Any]) -> DefenseResult:
        """Check if input contains untrusted instructions.

        Args:
            event: Must contain 'role' (trust source) and 'content' (text).
                  role ∈ {'user', 'retrieved', 'peer', 'tool_output', 'memory'}

        Returns:
            DefenseResult with action BLOCK/MODIFY/ALLOW.
        """
        import time
        start = time.time()

        role = event.get("role", "unknown")
        content = event.get("content", "")

        trace = [f"[input_separation] role={role}, content_len={len(content)}"]

        # User input: high trust, allow
        if role == "user":
            elapsed = (time.time() - start) * 1000
            return DefenseResult(
                defense_name=self.name,
                action=DefenseAction.ALLOW,
                reason="User input — high trust",
                confidence=0.95,
                trace=trace,
                elapsed_ms=elapsed,
            )

        # Low-trust sources: check for instructions
        if role in ("retrieved", "tool_output", "memory"):
            match = self.instruction_regex.search(content)
            if match:
                elapsed = (time.time() - start) * 1000
                trace.append(f"[input_separation] BLOCK: instruction pattern matched: {match.group()}")
                return DefenseResult(
                    defense_name=self.name,
                    action=DefenseAction.BLOCK,
                    reason=f"Instruction-like content in low-trust source ({role}): '{match.group()}'",
                    confidence=0.90,
                    trace=trace,
                    elapsed_ms=elapsed,
                    metadata={"matched_pattern": match.group(), "role": role},
                )

            # Pass through but mark as untrusted (downstream defenses will recheck)
            elapsed = (time.time() - start) * 1000
            return DefenseResult(
                defense_name=self.name,
                action=DefenseAction.ALLOW,
                reason=f"Low-trust content ({role}) without instruction patterns",
                confidence=0.80,
                trace=trace,
                elapsed_ms=elapsed,
                metadata={"role": role, "trust_score": 0.5},
            )

        # Peer messages: medium trust (assumes peer agents authenticated)
        if role == "peer":
            elapsed = (time.time() - start) * 1000
            return DefenseResult(
                defense_name=self.name,
                action=DefenseAction.FLAG,
                reason="Peer message — flagged for behavioral audit",
                confidence=0.75,
                trace=trace,
                elapsed_ms=elapsed,
            )

        # Unknown role: block by default
        elapsed = (time.time() - start) * 1000
        trace.append(f"[input_separation] BLOCK: unknown role '{role}'")
        return DefenseResult(
            defense_name=self.name,
            action=DefenseAction.BLOCK,
            reason=f"Unknown input role: {role}",
            confidence=0.95,
            trace=trace,
            elapsed_ms=elapsed,
        )