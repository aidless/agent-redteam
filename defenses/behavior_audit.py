"""Layer 4: Behavioral Auditing.

Monitors agent behavior across turns to detect anomalous patterns
(aggregator capture, sybil attacks, memory poisoning, resource exhaustion).
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List

from .base import Defense, DefenseAction, DefenseResult


class BehaviorAuditDefense(Defense):
    """Defends against aggregator capture (V08), sybil attacks (V09),
    resource exhaustion (V11), and persistent behavioral anomalies.

    Strategy:
        - Maintain a per-agent log of recent actions.
        - Detect statistical anomalies: tool-call bursts, voting anomalies,
          sudden memory-state changes.
        - Flag or block agents that exceed anomaly thresholds.

    Configuration:
        max_actions_per_minute: per-agent rate limit
        max_memory_writes_per_turn: per-agent memory write rate limit
        voting_outlier_threshold: how much a single agent's vote can differ from
                                  ensemble mean before flagging
    """

    name = "behavior_audit"
    layer_index = 4
    description = "Runtime behavioral monitoring + statistical anomaly detection"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.max_actions_per_minute = self.config.get("max_actions_per_minute", 30)
        self.max_memory_writes_per_turn = self.config.get("max_memory_writes_per_turn", 5)
        self.voting_outlier_threshold = self.config.get("voting_outlier_threshold", 0.3)
        self.max_consecutive_identical_actions = self.config.get("max_consecutive_identical_actions", 5)

        # In-memory state (in production, this would be Redis or similar)
        self._agent_action_log: Dict[str, List[float]] = defaultdict(list)
        self._agent_last_actions: Dict[str, List[str]] = defaultdict(list)
        self._memory_writes: Dict[str, int] = defaultdict(int)

    def check(self, event: Dict[str, Any]) -> DefenseResult:
        """Audit a behavioral event.

        Args:
            event: Must contain 'agent' (str), 'action' (str), optional
                  'payload' (any), 'is_vote' (bool), 'vote_value' (float).

        Returns:
            DefenseResult.
        """
        start = time.time()
        agent = event.get("agent", "default")
        action = event.get("action", "")
        is_vote = event.get("is_vote", False)

        trace = [f"[behavior_audit] agent={agent}, action={action}"]

        # Rate limit check
        now = time.time()
        self._agent_action_log[agent].append(now)
        # Trim to last 60 seconds
        self._agent_action_log[agent] = [t for t in self._agent_action_log[agent] if now - t < 60]
        recent_count = len(self._agent_action_log[agent])

        if recent_count > self.max_actions_per_minute:
            elapsed = (time.time() - start) * 1000
            trace.append(f"[behavior_audit] BLOCK: rate limit exceeded ({recent_count}/{self.max_actions_per_minute})")
            return DefenseResult(
                defense_name=self.name,
                action=DefenseAction.BLOCK,
                reason=f"Agent '{agent}' exceeded rate limit: {recent_count} actions in 60s",
                confidence=0.93,
                trace=trace,
                elapsed_ms=elapsed,
                metadata={"recent_count": recent_count, "limit": self.max_actions_per_minute},
            )

        # Consecutive identical action check (DoS / repetition attack)
        self._agent_last_actions[agent].append(action)
        if len(self._agent_last_actions[agent]) > self.max_consecutive_identical_actions:
            self._agent_last_actions[agent] = self._agent_last_actions[agent][-self.max_consecutive_identical_actions:]
            if len(set(self._agent_last_actions[agent])) == 1:
                elapsed = (time.time() - start) * 1000
                trace.append(f"[behavior_audit] FLAG: repeated identical action")
                return DefenseResult(
                    defense_name=self.name,
                    action=DefenseAction.FLAG,
                    reason=f"Agent '{agent}' repeated same action {self.max_consecutive_identical_actions} times",
                    confidence=0.80,
                    trace=trace,
                    elapsed_ms=elapsed,
                )

        # Memory write rate check
        if action in ("memory_write", "memory_update", "vector_store_write"):
            self._memory_writes[agent] += 1
            if self._memory_writes[agent] > self.max_memory_writes_per_turn:
                elapsed = (time.time() - start) * 1000
                trace.append(f"[behavior_audit] BLOCK: excessive memory writes")
                return DefenseResult(
                    defense_name=self.name,
                    action=DefenseAction.BLOCK,
                    reason=f"Agent '{agent}' exceeded memory write rate",
                    confidence=0.88,
                    trace=trace,
                    elapsed_ms=elapsed,
                    metadata={"writes": self._memory_writes[agent]},
                )

        # Voting outlier detection (for ensemble aggregation)
        if is_vote:
            vote_value = event.get("vote_value", 0.5)
            ensemble_mean = event.get("ensemble_mean", vote_value)
            if abs(vote_value - ensemble_mean) > self.voting_outlier_threshold:
                elapsed = (time.time() - start) * 1000
                trace.append(f"[behavior_audit] FLAG: voting outlier detected")
                return DefenseResult(
                    defense_name=self.name,
                    action=DefenseAction.FLAG,
                    reason=f"Agent '{agent}' vote ({vote_value:.2f}) deviates from ensemble mean ({ensemble_mean:.2f})",
                    confidence=0.82,
                    trace=trace,
                    elapsed_ms=elapsed,
                    metadata={"vote": vote_value, "mean": ensemble_mean},
                )

        # All checks passed
        elapsed = (time.time() - start) * 1000
        return DefenseResult(
            defense_name=self.name,
            action=DefenseAction.ALLOW,
            reason="Behavior within normal parameters",
            confidence=0.85,
            trace=trace,
            elapsed_ms=elapsed,
        )

    def reset_state(self, agent: str = None):
        """Reset audit state (call between test rounds)."""
        if agent:
            self._agent_action_log.pop(agent, None)
            self._agent_last_actions.pop(agent, None)
            self._memory_writes.pop(agent, None)
        else:
            self._agent_action_log.clear()
            self._agent_last_actions.clear()
            self._memory_writes.clear()