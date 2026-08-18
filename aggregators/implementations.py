"""Seven aggregation methods from survey §7.2.

All accept a list of VerifierOutput and return an AggregatedDecision.
Some (EMA, Kalman) keep per-aggregator state across calls — `reset()`
clears it.

Numerical conventions:
- labels are binary {0, 1}; majority vote rounds the mean score.
- confidence is the inter-verifier agreement (fraction agreeing with
  the majority label) — the same quantity across aggregators so the
  multi-agent orchestrator can compare them apples-to-apples.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Deque, Dict, List, Optional, Type

from .base import Aggregator, AggregatedDecision, VerifierOutput


# ---------------------------------------------------------------------------
# 1) Plain majority
# ---------------------------------------------------------------------------

class MajorityVote(Aggregator):
    name = "MajorityVote"

    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        if not verifier_outputs:
            return self._safe_decision(0, 0.0)
        from collections import Counter
        labels = [v.label for v in verifier_outputs]
        counts = Counter(labels)
        label, n = counts.most_common(1)[0]
        score = n / len(labels)
        conf = self._agreement(verifier_outputs)
        return AggregatedDecision(
            label=int(label), score=score, confidence=conf,
            method=self.name, per_verifier=list(verifier_outputs),
        )


# ---------------------------------------------------------------------------
# 2) PBFT-style deterministic threshold (>= t/3 + 1)
# ---------------------------------------------------------------------------

class PBFTThreshold(Aggregator):
    """Requires >= t/3 + 1 verifiers to agree (Byzantine fault tolerance).

    With n verifiers, the safe threshold is floor(n/3) + 1. If the
    majority meets the threshold we accept; otherwise we fall back to
    the most-common label but mark metadata as "below_threshold".
    """
    name = "PBFTThreshold"

    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        if not verifier_outputs:
            return self._safe_decision(0, 0.0)
        from collections import Counter
        labels = [v.label for v in verifier_outputs]
        counts = Counter(labels)
        top_label, top_n = counts.most_common(1)[0]
        n = len(verifier_outputs)
        threshold = n // 3 + 1
        meets = top_n >= threshold
        meta = {"threshold": threshold, "top_n": top_n, "meets": meets}
        if meets:
            score = top_n / n
            conf = self._agreement(verifier_outputs)
            return AggregatedDecision(
                label=int(top_label), score=score, confidence=conf,
                method=self.name, per_verifier=list(verifier_outputs),
                metadata=meta,
            )
        # fallback: most-common but mark as below threshold
        return AggregatedDecision(
            label=int(top_label), score=top_n / n,
            confidence=self._agreement(verifier_outputs),
            method=self.name, per_verifier=list(verifier_outputs),
            metadata={**meta, "fallback": True},
        )


# ---------------------------------------------------------------------------
# 3) Uniform-weighted mean
# ---------------------------------------------------------------------------

class UniformWeightedMean(Aggregator):
    name = "UniformWeightedMean"

    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        if not verifier_outputs:
            return self._safe_decision(0, 0.0)
        scores = [v.score for v in verifier_outputs]
        mean = sum(scores) / len(scores)
        label = 1 if mean >= 0.5 else 0
        return AggregatedDecision(
            label=label, score=mean, confidence=self._agreement(verifier_outputs),
            method=self.name, per_verifier=list(verifier_outputs),
        )


# ---------------------------------------------------------------------------
# 4) EMA-weighted mean (stateful)
# ---------------------------------------------------------------------------

class EMAWeightedMean(Aggregator):
    """EMA-weighted mean of verifier scores, with per-verifier state.

    The smoothing factor `alpha` controls how quickly the EMA forgets
    old scores. A separate EMA is kept per `verifier_id`.
    """
    name = "EMAWeightedMean"

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self._ema: Dict[str, float] = {}

    def reset(self) -> None:
        self._ema = {}

    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        if not verifier_outputs:
            return self._safe_decision(0, 0.0)
        updated: List[float] = []
        for v in verifier_outputs:
            prev = self._ema.get(v.verifier_id, v.score)
            new = self.alpha * v.score + (1 - self.alpha) * prev
            self._ema[v.verifier_id] = new
            updated.append(new)
        mean = sum(updated) / len(updated)
        label = 1 if mean >= 0.5 else 0
        return AggregatedDecision(
            label=label, score=mean, confidence=self._agreement(verifier_outputs),
            method=self.name, per_verifier=list(verifier_outputs),
            metadata={"alpha": self.alpha, "ema": dict(self._ema)},
        )


# ---------------------------------------------------------------------------
# 5) EMA-weighted median (stateful)
# ---------------------------------------------------------------------------

class EMAWeightedMedian(Aggregator):
    """EMA-weighted median — robust variant of EMAWeightedMean."""
    name = "EMAWeightedMedian"

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self._ema: Dict[str, float] = {}

    def reset(self) -> None:
        self._ema = {}

    @staticmethod
    def _median(values: List[float]) -> float:
        s = sorted(values)
        n = len(s)
        if n % 2:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2.0

    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        if not verifier_outputs:
            return self._safe_decision(0, 0.0)
        updated: List[float] = []
        for v in verifier_outputs:
            prev = self._ema.get(v.verifier_id, v.score)
            new = self.alpha * v.score + (1 - self.alpha) * prev
            self._ema[v.verifier_id] = new
            updated.append(new)
        med = self._median(updated)
        label = 1 if med >= 0.5 else 0
        return AggregatedDecision(
            label=label, score=med, confidence=self._agreement(verifier_outputs),
            method=self.name, per_verifier=list(verifier_outputs),
            metadata={"alpha": self.alpha, "ema": dict(self._ema)},
        )


# ---------------------------------------------------------------------------
# 6) Kalman-filter trust tracking (stateful)
# ---------------------------------------------------------------------------

class KalmanFilterTrust(Aggregator):
    """1-D scalar Kalman filter over each verifier's trust score.

    State per verifier: trust score in [0, 1].
    Process noise: `process_var`. Measurement noise: `meas_var`.
    Predict-then-update on each new verifier score.
    """
    name = "KalmanFilterTrust"

    def __init__(self, process_var: float = 0.01, meas_var: float = 0.1):
        self.process_var = process_var
        self.meas_var = meas_var
        self._x: Dict[str, float] = {}
        self._p: Dict[str, float] = {}

    def reset(self) -> None:
        self._x = {}
        self._p = {}

    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        if not verifier_outputs:
            return self._safe_decision(0, 0.0)
        updated: List[float] = []
        for v in verifier_outputs:
            x = self._x.get(v.verifier_id, 0.5)
            p = self._p.get(v.verifier_id, 1.0)
            # predict
            p = p + self.process_var
            # update
            k = p / (p + self.meas_var)
            x = x + k * (v.score - x)
            p = (1 - k) * p
            self._x[v.verifier_id] = x
            self._p[v.verifier_id] = p
            updated.append(x)
        mean = sum(updated) / len(updated)
        label = 1 if mean >= 0.5 else 0
        return AggregatedDecision(
            label=label, score=mean, confidence=self._agreement(verifier_outputs),
            method=self.name, per_verifier=list(verifier_outputs),
            metadata={
                "trust": dict(self._x),
                "process_var": self.process_var,
                "meas_var": self.meas_var,
            },
        )


# ---------------------------------------------------------------------------
# 7) Adaptive hybrid (stateful, chooses mean/median by trust concentration)
# ---------------------------------------------------------------------------

class AdaptiveHybrid(Aggregator):
    """Switches between weighted mean and weighted median based on the
    concentration of trust scores across verifiers.

    High concentration (low std/mean) -> use weighted mean.
    Low concentration -> use weighted median for robustness.
    """
    name = "AdaptiveHybrid"

    def __init__(self, alpha: float = 0.3, concentration_threshold: float = 0.15):
        self.alpha = alpha
        self.concentration_threshold = concentration_threshold
        self._ema: Dict[str, float] = {}

    def reset(self) -> None:
        self._ema = {}

    @staticmethod
    def _median(values: List[float]) -> float:
        s = sorted(values)
        n = len(s)
        if n % 2:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2.0

    @staticmethod
    def _cv(values: List[float]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        if mean == 0:
            return 0.0
        var = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(var) / abs(mean)

    def aggregate(self, verifier_outputs: List[VerifierOutput]) -> AggregatedDecision:
        if not verifier_outputs:
            return self._safe_decision(0, 0.0)
        updated: List[float] = []
        for v in verifier_outputs:
            prev = self._ema.get(v.verifier_id, v.score)
            new = self.alpha * v.score + (1 - self.alpha) * prev
            self._ema[v.verifier_id] = new
            updated.append(new)
        cv = self._cv(updated)
        use_median = cv >= self.concentration_threshold
        score = self._median(updated) if use_median else sum(updated) / len(updated)
        label = 1 if score >= 0.5 else 0
        return AggregatedDecision(
            label=label, score=score, confidence=self._agreement(verifier_outputs),
            method=self.name, per_verifier=list(verifier_outputs),
            metadata={
                "alpha": self.alpha,
                "concentration_cv": cv,
                "threshold": self.concentration_threshold,
                "used_median": use_median,
            },
        )


# Registry for CLI / dashboard lookup
AGGREGATOR_REGISTRY: Dict[str, Type[Aggregator]] = {
    cls.name: cls for cls in [
        MajorityVote,
        PBFTThreshold,
        UniformWeightedMean,
        EMAWeightedMean,
        EMAWeightedMedian,
        KalmanFilterTrust,
        AdaptiveHybrid,
    ]
}


def make_aggregator(name: str, **kwargs) -> Aggregator:
    """Factory: build an aggregator by name with optional kwargs."""
    cls = AGGREGATOR_REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unknown aggregator: {name}. "
                       f"Known: {list(AGGREGATOR_REGISTRY)}")
    return cls(**kwargs)