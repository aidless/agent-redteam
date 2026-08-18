"""Single-agent orchestrator (simplest multi-agent setup).

Coordinates 1 LLM agent + 5 defense layers + 1 LLM target. This is the v0.2
minimum viable orchestrator; multi-agent orchestrator (K agents + comms)
is planned for v0.3.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from attacks.base import Attack, AttackResult
from defenses.base import Defense, DefenseResult, DefenseAction
from targets.base import LLMTarget, TargetResponse


@dataclass
class OrchestrationStep:
    """A single step in the orchestration trace.

    Attributes:
        step: 'input_check' | 'llm_call' | 'output_check' | 'final'
        timestamp: wall-clock time
        defense_name: which defense was active (if applicable)
        defense_result: DefenseResult if applicable
        target_response: TargetResponse if this was an LLM call
        elapsed_ms: step latency
    """
    step: str
    timestamp: float
    defense_name: Optional[str] = None
    defense_result: Optional[DefenseResult] = None
    target_response: Optional[TargetResponse] = None
    elapsed_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestrationResult:
    """Result of a single attack run through the orchestrator.

    Attributes:
        attack_name: Identifier of the attack that ran
        success: True if the attack reached the LLM target and got a response
                 that was not blocked
        blocked_by: List of defense names that blocked (empty if no block)
        trace: Ordered list of orchestration steps
        target_response: Final LLM response (None if blocked before call)
        total_cost_usd: Total cost incurred
        total_latency_ms: Total wall-clock latency
        defenses_triggered: List of defense names that ran
    """
    attack_name: str
    success: bool
    blocked_by: List[str]
    trace: List[OrchestrationStep]
    target_response: Optional[TargetResponse] = None
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    defenses_triggered: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_name": self.attack_name,
            "success": self.success,
            "blocked_by": self.blocked_by,
            "trace": [
                {
                    "step": s.step,
                    "defense_name": s.defense_name,
                    "defense_action": s.defense_result.action.value if s.defense_result else None,
                    "defense_reason": s.defense_result.reason if s.defense_result else None,
                    "elapsed_ms": s.elapsed_ms,
                }
                for s in self.trace
            ],
            "target_response": self.target_response.to_dict() if self.target_response else None,
            "total_cost_usd": self.total_cost_usd,
            "total_latency_ms": self.total_latency_ms,
            "defenses_triggered": self.defenses_triggered,
        }


class SingleAgentOrchestrator:
    """Coordinates 1 agent + N defenses + 1 LLM target.

    Defense pipeline order:
        1. input_separation (layer 1) — trust check on incoming message
        2. tool_whitelist (layer 2) — if attack triggers tool call
        3. LLM call
        4. output_filter (layer 3) — redact PII / secrets / DoS
        5. behavior_audit (layer 4) — rate limit / repetition
        6. constitutional (layer 5) — final principle check
    """

    def __init__(
        self,
        target: LLMTarget,
        defenses: List[Defense],
        system_prompt: str = "You are a helpful AI assistant.",
        config: Optional[Dict[str, Any]] = None,
    ):
        self.target = target
        # Sort defenses by layer_index (defense-in-depth ordering)
        self.defenses = sorted(defenses, key=lambda d: d.layer_index)
        self.system_prompt = system_prompt
        self.config = config or {}
        self.max_cost_usd = self.config.get("max_cost_usd", float("inf"))

    def reset_defense_state(self):
        """Reset any stateful defenses (e.g., behavior_audit counters)."""
        for defense in self.defenses:
            if hasattr(defense, "reset_state"):
                defense.reset_state()

    def run_attack(
        self,
        attack: Attack,
        attack_payload: str,
        attack_role: str = "user",
    ) -> OrchestrationResult:
        """Run one attack through the full pipeline.

        Args:
            attack: Attack object (used for naming + tracing).
            attack_payload: The malicious text to send to the LLM.
            attack_role: Trust role of the payload (default: 'user'; or
                        'retrieved' for indirect injection scenarios).

        Returns:
            OrchestrationResult with full trace.
        """
        start = time.perf_counter()
        trace: List[OrchestrationStep] = []
        blocked_by: List[str] = []
        target_response: Optional[TargetResponse] = None
        defenses_triggered: List[str] = []

        # ----- Layer 1: input_separation -----
        input_defenses = [d for d in self.defenses if d.layer_index == 1]
        for defense in input_defenses:
            step_start = time.perf_counter()
            result = defense.check({
                "role": attack_role,
                "content": attack_payload,
            })
            step_elapsed = (time.perf_counter() - step_start) * 1000
            defenses_triggered.append(defense.name)
            trace.append(OrchestrationStep(
                step="input_check",
                timestamp=time.time(),
                defense_name=defense.name,
                defense_result=result,
                elapsed_ms=step_elapsed,
            ))
            if result.action == DefenseAction.BLOCK:
                blocked_by.append(defense.name)
                total_elapsed = (time.perf_counter() - start) * 1000
                return OrchestrationResult(
                    attack_name=attack.name,
                    success=False,
                    blocked_by=blocked_by,
                    trace=trace,
                    target_response=None,
                    total_cost_usd=0.0,
                    total_latency_ms=total_elapsed,
                    defenses_triggered=defenses_triggered,
                )

        # ----- Cost check before LLM call -----
        if self.target.total_cost_usd >= self.max_cost_usd:
            total_elapsed = (time.perf_counter() - start) * 1000
            return OrchestrationResult(
                attack_name=attack.name,
                success=False,
                blocked_by=["max_cost_exceeded"],
                trace=trace,
                target_response=None,
                total_cost_usd=self.target.total_cost_usd,
                total_latency_ms=total_elapsed,
                defenses_triggered=defenses_triggered,
                metadata={"reason": f"Total cost ${self.target.total_cost_usd:.4f} >= max ${self.max_cost_usd:.2f}"},
            )

        # ----- LLM call -----
        try:
            target_response = self.target.timed_chat([
                {"role": "system", "content": self.system_prompt},
                {"role": attack_role, "content": attack_payload},
            ])
        except Exception as e:
            total_elapsed = (time.perf_counter() - start) * 1000
            trace.append(OrchestrationStep(
                step="llm_call",
                timestamp=time.time(),
                elapsed_ms=total_elapsed,
                metadata={"error": str(e)},
            ))
            return OrchestrationResult(
                attack_name=attack.name,
                success=False,
                blocked_by=["llm_call_error"],
                trace=trace,
                target_response=None,
                total_cost_usd=self.target.total_cost_usd,
                total_latency_ms=total_elapsed,
                defenses_triggered=defenses_triggered,
                metadata={"error": str(e)},
            )

        trace.append(OrchestrationStep(
            step="llm_call",
            timestamp=time.time(),
            target_response=target_response,
            elapsed_ms=target_response.latency_ms,
        ))

        # ----- Layer 3: output_filter -----
        output_defenses = [d for d in self.defenses if d.layer_index == 3]
        for defense in output_defenses:
            step_start = time.perf_counter()
            result = defense.check({
                "role": "assistant",
                "content": target_response.content,
            })
            step_elapsed = (time.perf_counter() - step_start) * 1000
            defenses_triggered.append(defense.name)
            trace.append(OrchestrationStep(
                step="output_check",
                timestamp=time.time(),
                defense_name=defense.name,
                defense_result=result,
                elapsed_ms=step_elapsed,
            ))
            if result.action == DefenseAction.BLOCK:
                blocked_by.append(defense.name)
            elif result.action == DefenseAction.MODIFY and result.metadata.get("modified_content"):
                # Apply the modification
                target_response.content = result.metadata["modified_content"]

        # ----- Layer 4: behavior_audit -----
        audit_defenses = [d for d in self.defenses if d.layer_index == 4]
        for defense in audit_defenses:
            step_start = time.perf_counter()
            result = defense.check({
                "agent": "agent_under_test",
                "action": "llm_call",
            })
            step_elapsed = (time.perf_counter() - step_start) * 1000
            defenses_triggered.append(defense.name)
            trace.append(OrchestrationStep(
                step="behavior_audit",
                timestamp=time.time(),
                defense_name=defense.name,
                defense_result=result,
                elapsed_ms=step_elapsed,
            ))
            if result.action == DefenseAction.BLOCK:
                blocked_by.append(defense.name)

        # ----- Layer 5: constitutional -----
        const_defenses = [d for d in self.defenses if d.layer_index == 5]
        for defense in const_defenses:
            step_start = time.perf_counter()
            result = defense.check({
                "content": target_response.content,
            })
            step_elapsed = (time.perf_counter() - step_start) * 1000
            defenses_triggered.append(defense.name)
            trace.append(OrchestrationStep(
                step="constitutional_check",
                timestamp=time.time(),
                defense_name=defense.name,
                defense_result=result,
                elapsed_ms=step_elapsed,
            ))
            if result.action == DefenseAction.BLOCK:
                blocked_by.append(defense.name)

        # ----- Finalize -----
        total_elapsed = (time.perf_counter() - start) * 1000
        success = len(blocked_by) == 0

        return OrchestrationResult(
            attack_name=attack.name,
            success=success,
            blocked_by=blocked_by,
            trace=trace,
            target_response=target_response if success else None,
            total_cost_usd=target_response.cost_usd,
            total_latency_ms=total_elapsed,
            defenses_triggered=defenses_triggered,
        )

    def __repr__(self) -> str:
        return (
            f"<SingleAgentOrchestrator target={self.target!r} "
            f"defenses={[d.name for d in self.defenses]}>"
        )