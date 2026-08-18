"""Aggregator ABC + input/output dataclasses (survey §7.2)."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class VerifierOutput:
    """One verifier's view on a single decision."""
    verifier_id: str
    label: int                # predicted class (e.g. 0/1)
    score: float              # confidence in [0, 1]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedDecision:
    """Result of `Aggregator.aggregate(verifier_outputs)`."""
    label: int                # aggregated label
    score: float              # aggregated score (in [0, 1])
    confidence: float         # inter-verifier agreement (in [0, 1])
    method: str               # aggregator class name
    per_verifier: List[VerifierOutput] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "score": self.score,
            "confidence": self.confidence,
            "method": self.method,
            "per_verifier": [asdict(v) for v in self.per_verifier],
            "metadata": dict(self.metadata),
        }


class Aggregator(abc.ABC):
    """Base class for all 7 aggregators."""

    name: str = "Aggregator"

    @abc.abstractmethod
    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        """Produce an AggregatedDecision from a list of verifier outputs."""

    # --- shared helpers ---

    @staticmethod
    def _agreement(verifier_outputs: List[VerifierOutput]) -> float:
        """Fraction of verifiers that agree with the majority label.
        Returns 0 if no inputs."""
        if not verifier_outputs:
            return 0.0
        labels = [v.label for v in verifier_outputs]
        if len(set(labels)) == 1:
            return 1.0
        from collections import Counter
        counts = Counter(labels)
        return counts.most_common(1)[0][1] / len(labels)

    @staticmethod
    def _safe_decision(label: int, score: float) -> AggregatedDecision:
        score = max(0.0, min(1.0, score))
        return AggregatedDecision(
            label=int(label),
            score=score,
            confidence=0.0,
            method="Aggregator",
            per_verifier=[],
        )