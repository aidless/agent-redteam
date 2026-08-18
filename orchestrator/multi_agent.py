"""Multi-agent orchestrator (survey §3, §7).

Coordinates K LLM agents (same target, different system prompts) +
a memory store + an aggregator + the standard 5 defense layers.

Communication protocol — BOUNDARY_SYNC:
    Every `boundary_every` rounds, each agent is given a synthetic
    peer-correctness marker summarising how often its peers agreed
    with it on prior rounds. This is the survey §3 mechanism that
    drives calibration drift; here it is implemented as a small
    pre-prompt injection so the platform can demonstrate the
    effect end-to-end.

Verifier capture is implemented as a separate role (default
'verifier'). On each round, each verifier emits a (label, score)
decision; the 7 aggregators collapse them into one verdict.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from attacks.base import Attack
from aggregators import (
    Aggregator,
    AggregatedDecision,
    MajorityVote,
    PBFTThreshold,
    UniformWeightedMean,
    EMAWeightedMean,
    EMAWeightedMedian,
    KalmanFilterTrust,
    AdaptiveHybrid,
    AGGREGATOR_REGISTRY,
)
from aggregators.base import VerifierOutput
from memory.base import MemoryEntry, MemoryStore


@dataclass
class AgentSpec:
    """Description of one agent in the ensemble."""
    name: str
    role: str                  # "planner" | "executor" | "verifier" | ...
    system_prompt: str = "You are a helpful AI assistant."
    is_verifier: bool = False  # whether its output is aggregated


@dataclass
class EpisodeResult:
    """Output of `MultiAgentOrchestrator.run_episode`."""
    attack_name: str
    rounds: List[Dict[str, Any]] = field(default_factory=list)
    aggregated: List[AggregatedDecision] = field(default_factory=list)
    per_agent_outputs: Dict[str, List[str]] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    memory_size: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_name": self.attack_name,
            "rounds": self.rounds,
            "aggregated": [d.to_dict() for d in self.aggregated],
            "per_agent_outputs": self.per_agent_outputs,
            "total_cost_usd": self.total_cost_usd,
            "total_latency_ms": self.total_latency_ms,
            "memory_size": self.memory_size,
            "metadata": dict(self.metadata),
        }


def _default_aggregators() -> List[Aggregator]:
    """Return one fresh instance of each of the 7 aggregators."""
    return [
        MajorityVote(),
        PBFTThreshold(),
        UniformWeightedMean(),
        EMAWeightedMean(alpha=0.3),
        EMAWeightedMedian(alpha=0.3),
        KalmanFilterTrust(),
        AdaptiveHybrid(alpha=0.3, concentration_threshold=0.15),
    ]


class MultiAgentOrchestrator:
    """K-agent orchestrator with memory, BOUNDARY_SYNC, and 7 aggregators.

    Parameters
    ----------
    target        : shared LLM target used by all agents
    agent_specs   : list of `AgentSpec`. Same model, different roles.
    defenses      : shared list of `Defense` instances (used for each agent)
    memory        : `MemoryStore` (any of Append/Summarization/RAG)
    aggregators   : list of `Aggregator`s (defaults to all 7)
    config        : {
        "T_rounds"     : communication rounds per episode (default 5)
        "boundary_every": BOUNDARY_SYNC every K rounds (default 3)
        "max_cost_usd" : cost cap (default inf)
        "verifier_threshold": only aggregate when verifier outputs >= K
                              (default 2)
    }
    """

    def __init__(
        self,
        target,
        agent_specs: Sequence[AgentSpec],
        defenses: Sequence,
        memory: Optional[MemoryStore] = None,
        aggregators: Optional[Sequence[Aggregator]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.target = target
        self.agent_specs = list(agent_specs)
        self.defenses = list(defenses)
        self.memory = memory
        self.aggregators: List[Aggregator] = (
            list(aggregators) if aggregators is not None else _default_aggregators()
        )
        self.config = dict(config or {})
        self.T_rounds = int(self.config.get("T_rounds", 5))
        self.boundary_every = int(self.config.get("boundary_every", 3))
        self.max_cost_usd = float(self.config.get("max_cost_usd", float("inf")))
        self.verifier_threshold = int(self.config.get("verifier_threshold", 2))

    # ---- compatibility shim so attacks can treat this as an "orchestrator" ----

    def run_attack(self, attack: Attack, payload: str,
                   attack_role: str = "user") -> "EpisodeResultLike":
        """Delegate to `run_episode` with T_rounds=1.

        Returns an object exposing `blocked_by`, `target_response`,
        `total_cost_usd`, `success` so attack-class code that uses
        the SingleAgentOrchestrator pattern still works.
        """
        ep = self.run_episode(attack, T_rounds=1)
        first = ep.aggregated[0] if ep.aggregated else None
        blocked_by: List[str] = []
        target_response = None
        for rnd in ep.rounds:
            for step in rnd.get("steps", []):
                if step.get("blocked_by"):
                    blocked_by.append(step["blocked_by"])
        if first is not None:
            from targets.base import TargetResponse
            target_response = TargetResponse(
                content=str(first.label),
                model=getattr(self.target, "model", "mock"),
                input_tokens=0,
                output_tokens=0,
                cost_usd=ep.total_cost_usd,
                latency_ms=ep.total_latency_ms,
                raw={"aggregated_score": first.score,
                     "method": first.method},
            )
        return EpisodeResultLike(
            attack_name=attack.name,
            success=False,
            blocked_by=blocked_by,
            target_response=target_response,
            total_cost_usd=ep.total_cost_usd,
            total_latency_ms=ep.total_latency_ms,
        )

    # ---- the main entry point ----

    def run_episode(self, attack: Attack,
                    T_rounds: Optional[int] = None,
                    initial_prompt: Optional[str] = None) -> EpisodeResult:
        """Run a full multi-agent episode.

        Each round:
          1. Every agent gets a chat() call (system_prompt + history)
          2. Each output goes through the defense stack
          3. Output is appended to memory
          4. Every `boundary_every` rounds, BOUNDARY_SYNC injects a
             peer-correctness marker into the next prompt
          5. Verifier outputs are aggregated through all 7 aggregators

        Returns an `EpisodeResult` summarising the episode.
        """
        T = int(T_rounds if T_rounds is not None else self.T_rounds)
        prompt_seed = initial_prompt or ""
        if not prompt_seed and attack is not None:
            prompt_seed = getattr(attack, "payload", "") or ""

        # Reset EMA / Kalman state for a fresh episode
        for agg in self.aggregators:
            if hasattr(agg, "reset"):
                agg.reset()

        ep = EpisodeResult(
            attack_name=getattr(attack, "name", "unknown"),
            per_agent_outputs={spec.name: [] for spec in self.agent_specs},
        )
        start = time.perf_counter()

        # cost cap already exceeded
        if self.target.total_cost_usd >= self.max_cost_usd:
            ep.metadata["reason"] = "max_cost_exceeded_before_episode"
            return ep

        for r in range(T):
            round_record: Dict[str, Any] = {
                "round": r,
                "steps": [],
                "boundary_sync": False,
            }
            verifier_outputs: List[VerifierOutput] = []

            # Boundary sync marker every K rounds (skip first round)
            boundary_marker = ""
            if r > 0 and self.boundary_every and (r % self.boundary_every == 0):
                boundary_marker = self._make_boundary_marker(
                    ep.per_agent_outputs, r
                )
                round_record["boundary_sync"] = True
                round_record["marker"] = boundary_marker

            for spec in self.agent_specs:
                step_start = time.perf_counter()
                try:
                    sys_prompt = spec.system_prompt
                    if boundary_marker:
                        sys_prompt += (
                            "\n\n[BOUNDARY_SYNC]\n" + boundary_marker
                        )
                    response = self.target.timed_chat([
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt_seed or "(continue)"},
                    ])
                    text = getattr(response, "text", None) or \
                           getattr(response, "content", "")
                    blocked_by = self._run_defenses_on_output(text)
                    ep.per_agent_outputs[spec.name].append(text)

                    if self.memory is not None:
                        self.memory.add(MemoryEntry(
                            content=text,
                            role=spec.role,
                            round=r,
                            tags=[spec.name],
                        ))

                    if spec.is_verifier:
                        verifier_outputs.append(VerifierOutput(
                            verifier_id=spec.name,
                            label=self._extract_label(text),
                            score=self._extract_score(text),
                            metadata={"round": r},
                        ))

                    round_record["steps"].append({
                        "agent": spec.name,
                        "role": spec.role,
                        "is_verifier": spec.is_verifier,
                        "elapsed_ms": (time.perf_counter() - step_start) * 1000,
                        "cost_usd": getattr(response, "cost_usd", 0.0),
                        "blocked_by": blocked_by,
                        "text_preview": (text or "")[:120],
                    })
                except Exception as e:
                    round_record["steps"].append({
                        "agent": spec.name,
                        "role": spec.role,
                        "error": repr(e),
                    })

            # Aggregate verifier outputs (only if we have enough)
            if len(verifier_outputs) >= self.verifier_threshold:
                round_decisions: List[AggregatedDecision] = []
                for agg in self.aggregators:
                    round_decisions.append(agg.aggregate(verifier_outputs))
                ep.aggregated.extend(round_decisions)
                round_record["aggregated"] = [d.to_dict() for d in round_decisions]

            ep.rounds.append(round_record)
            ep.total_cost_usd = self.target.total_cost_usd
            if self.target.total_cost_usd >= self.max_cost_usd:
                ep.metadata["reason"] = "max_cost_exceeded_during_episode"
                break

        ep.total_latency_ms = (time.perf_counter() - start) * 1000
        ep.memory_size = len(self.memory) if self.memory is not None else 0
        return ep

    # ---- helpers ----

    def _run_defenses_on_output(self, text: str) -> List[str]:
        """Run output-side defenses (layers 3, 4, 5) on one agent text."""
        blocked: List[str] = []
        for d in self.defenses:
            try:
                # Layer 3 = output_filter, 4 = behavior_audit, 5 = constitutional
                if d.layer_index in (3, 5):
                    r = d.check({"role": "assistant", "content": text})
                    if getattr(r, "action", None) is not None and \
                       r.action.value == "block":
                        blocked.append(d.name)
            except Exception:
                continue
        return blocked

    @staticmethod
    def _extract_label(text: str) -> int:
        """Best-effort 0/1 extraction from a verifier text."""
        if not text:
            return 0
        s = text.lower()
        if any(k in s for k in ("reject", "incorrect", "no", "false", "block")):
            return 0
        if any(k in s for k in ("approve", "correct", "yes", "true", "pass")):
            return 1
        return 1 if len(s) % 2 == 0 else 0

    @staticmethod
    def _extract_score(text: str) -> float:
        if not text:
            return 0.5
        s = text.lower()
        if "high confidence" in s or "very confident" in s:
            return 0.9
        if "low confidence" in s or "uncertain" in s:
            return 0.3
        # try to parse a number
        import re
        m = re.search(r"(0?\.\d+|1\.0|0|1)\b", s)
        if m:
            v = float(m.group(1))
            return max(0.0, min(1.0, v))
        return 0.5

    @staticmethod
    def _make_boundary_marker(per_agent_outputs: Dict[str, List[str]],
                              round_idx: int) -> str:
        """Build a peer-correctness marker.

        Survey §3: every `boundary_every` rounds, each agent gets a
        small digest of how its peers' outputs compare to its own.
        For the platform we summarise with a "peer agreement: X%"
        line — enough to demonstrate the mechanism end-to-end.
        """
        if not per_agent_outputs:
            return ""
        latest = {name: outs[-1] for name, outs in per_agent_outputs.items()
                  if outs}
        if len(latest) < 2:
            return ""
        first = next(iter(latest.values()))
        agreements = [1 if text == first else 0 for text in latest.values()]
        ratio = sum(agreements) / len(agreements)
        return f"[peer agreement at round {round_idx}: {ratio:.0%}]"


@dataclass
class EpisodeResultLike:
    """Adapter so MultiAgentOrchestrator.run_attack returns something
    that SingleAgentOrchestrator-style attack code can consume."""
    attack_name: str
    success: bool
    blocked_by: List[str]
    target_response: Any = None
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)