"""Pure-Python implementations of calibration metrics (survey §2.2).

All functions are deterministic, side-effect free, and tolerate edge cases
(zero denominators, empty inputs, all-identical vectors) gracefully so
they can be plugged into larger pipelines without preconditions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Iterable, List, Mapping, Sequence


# ---------------------------------------------------------------------------
# ECE — Expected Calibration Error (equal-width bins)
# ---------------------------------------------------------------------------

def ece(probs: Sequence[float], labels: Sequence[int], n_bins: int = 15) -> float:
    """Expected Calibration Error with `n_bins` equal-width bins.

    Parameters
    ----------
    probs  : sequence of confidence scores in [0, 1] (one per sample)
    labels : sequence of binary ground-truth labels in {0, 1}
    n_bins : number of equal-width bins (default 15 per [P4])

    Returns
    -------
    ece_value : float in [0, 1]. 0 = perfectly calibrated.

    Notes
    -----
    Equal-width bins in [0, 1] — bin i covers [i/n_bins, (i+1)/n_bins).
    A sample with prob == 1.0 falls in the last bin (closed on the right).
    """
    if n_bins <= 0:
        raise ValueError(f"n_bins must be positive, got {n_bins}")
    probs = list(probs)
    labels = list(labels)
    if len(probs) != len(labels):
        raise ValueError(
            f"probs and labels length mismatch: {len(probs)} vs {len(labels)}"
        )
    n = len(probs)
    if n == 0:
        return 0.0

    bin_totals = [0] * n_bins       # count per bin
    bin_correct = [0] * n_bins       # # of label == 1 per bin
    bin_conf_sum = [0.0] * n_bins    # sum of probs per bin

    for p, y in zip(probs, labels):
        # clip p to [0, 1] so out-of-range values do not crash
        p_clipped = max(0.0, min(1.0, float(p)))
        bin_idx = min(int(p_clipped * n_bins), n_bins - 1)
        bin_totals[bin_idx] += 1
        bin_conf_sum[bin_idx] += p_clipped
        if int(y) == 1:
            bin_correct[bin_idx] += 1

    ece_val = 0.0
    for i in range(n_bins):
        if bin_totals[i] == 0:
            continue
        acc = bin_correct[i] / bin_totals[i]
        conf = bin_conf_sum[i] / bin_totals[i]
        ece_val += (bin_totals[i] / n) * abs(acc - conf)
    return ece_val


# ---------------------------------------------------------------------------
# JSD — Jensen-Shannon Divergence
# ---------------------------------------------------------------------------

def jsd(p: Sequence[float], q: Sequence[float], eps: float = 1e-12) -> float:
    """Jensen-Shannon divergence between two probability distributions.

    JSD ∈ [0, 1] (base-2 log). Returns 0 if p == q.
    Distributions are auto-normalized; zero entries are smoothed with `eps`
    so the log does not blow up.
    """
    p_list = [max(0.0, float(x)) for x in p]
    q_list = [max(0.0, float(x)) for x in q]
    if len(p_list) != len(q_list):
        raise ValueError(
            f"p and q length mismatch: {len(p_list)} vs {len(q_list)}"
        )
    if not p_list:
        return 0.0
    p_sum = sum(p_list) or 1.0
    q_sum = sum(q_list) or 1.0
    p_n = [x / p_sum for x in p_list]
    q_n = [x / q_sum for x in q_list]
    m = [(a + b) / 2.0 for a, b in zip(p_n, q_n)]

    def _kl(a: Sequence[float], b: Sequence[float]) -> float:
        s = 0.0
        for ai, bi in zip(a, b):
            ai_e = ai if ai > 0 else eps
            bi_e = bi if bi > 0 else eps
            s += ai_e * math.log2(ai_e / bi_e)
        return s

    return 0.5 * (_kl(p_n, m) + _kl(q_n, m))


# ---------------------------------------------------------------------------
# H — Shannon entropy (normalized to [0, 1])
# ---------------------------------------------------------------------------

def entropy(distribution: Sequence[float], eps: float = 1e-12) -> float:
    """Normalized Shannon entropy in [0, 1] using log2.

    H = 0   if the distribution is a one-hot vector.
    H = 1   if the distribution is uniform over n categories.
    """
    vals = [max(0.0, float(x)) for x in distribution]
    total = sum(vals)
    if total <= 0 or not vals:
        return 0.0
    n = len(vals)
    h = 0.0
    for v in vals:
        if v <= 0:
            continue
        p = v / total
        h -= p * math.log2(p)
    max_h = math.log2(n) if n > 1 else 1.0
    if max_h <= 0:
        return 0.0
    return max(0.0, min(1.0, h / max_h))


# ---------------------------------------------------------------------------
# CV — coefficient of variation
# ---------------------------------------------------------------------------

def cv(values: Sequence[float]) -> float:
    """Coefficient of variation = std(values) / mean(values).

    Returns
    -------
    cv_value : float >= 0. Returns +inf when mean == 0 and values vary.
    Returns 0 when all values are identical (including the all-zeros case).
    """
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return 0.0
    mean = sum(vals) / n
    if mean == 0:
        return 0.0 if all(v == 0 for v in vals) else float("inf")
    var = sum((v - mean) ** 2 for v in vals) / n
    return math.sqrt(var) / abs(mean)


# ---------------------------------------------------------------------------
# gamma_temporal — 1-D Wasserstein-1 distance
# ---------------------------------------------------------------------------

def gamma_temporal(biased: Sequence[float], clean: Sequence[float]) -> float:
    """Wasserstein-1 distance between two empirical distributions of
    the same length.

    Computed on order statistics as (1/n) * sum_i |X_{(i)} - Y_{(i)}|.
    Lower = less bias propagation (used as Γ_temporal in [P5]).
    Empty inputs return 0; length mismatch raises.
    """
    b = list(biased)
    c = list(clean)
    if len(b) != len(c):
        raise ValueError(
            f"biased and clean length mismatch: {len(b)} vs {len(c)}"
        )
    if not b:
        return 0.0
    sb = sorted(float(x) for x in b)
    sc = sorted(float(x) for x in c)
    n = len(sb)
    return sum(abs(x - y) for x, y in zip(sb, sc)) / n


# ---------------------------------------------------------------------------
# gamma — coupling coefficient (survey §2.2 / [P2, P3])
# ---------------------------------------------------------------------------

def coupling(W_TV: Sequence[float], W_V: Sequence[float], eps: float = 1e-12) -> float:
    """γ = ||W_{T->V} - W_V||_2 / ||W_V||_2.

    Parameters
    ----------
    W_TV : verifier's preference weights after TTRL training
    W_V  : verifier's reference preference weights (clean / pre-training)

    Returns
    -------
    gamma : float >= 0. 0 = no coupling (T did not move V).
            +inf if ||W_V||_2 == 0 (caller's responsibility to interpret).
    """
    a = [float(x) for x in W_TV]
    b = [float(x) for x in W_V]
    if len(a) != len(b):
        raise ValueError(
            f"W_TV and W_V length mismatch: {len(a)} vs {len(b)}"
        )
    if not a:
        return 0.0
    diff_sq = sum((x - y) ** 2 for x, y in zip(a, b))
    norm_sq = sum(y * y for y in b)
    if norm_sq <= eps:
        return float("inf")
    return math.sqrt(diff_sq / norm_sq)


# ---------------------------------------------------------------------------
# impossibility triangle (survey §4.1)
# ---------------------------------------------------------------------------

def impossibility_triangle(
    gamma: float,
    H: float,
    CV: float,
    c_min: float = 1e-3,
) -> "ImpossibilityResult":
    """γ·H·CV ≥ c_min check from the impossibility triangle [P2, P3].

    Returns a small dataclass so callers can inspect all three values
    (the inequality, the product, and the threshold) without recomputing.
    """
    if min(gamma, H, CV) < 0:
        raise ValueError("gamma, H, CV must all be non-negative")
    product = gamma * H * CV
    return ImpossibilityResult(
        product=product,
        c_min=c_min,
        violated=product < c_min,
   )


@dataclass
class ImpossibilityResult:
    """Outcome of an impossibility-triangle evaluation."""
    product: float
    c_min: float
    violated: bool

    @property
    def passes(self) -> bool:
        """True when γ·H·CV ≥ c_min (the joint bound is satisfied)."""
        return not self.violated

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# CalibrationReport — convenience bundle
# ---------------------------------------------------------------------------

@dataclass
class CalibrationReport:
    """Bundle of all six metrics for one experiment.

    `from_map` builds a report from a dict so configs / dashboards can
    populate metrics without knowing the field order.
    """
    ece: float = 0.0
    jsd: float = 0.0
    entropy: float = 0.0
    cv: float = 0.0
    gamma_temporal: float = 0.0
    gamma: float = 0.0
    impossible: bool = False
    notes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_map(cls, m: Mapping[str, float]) -> "CalibrationReport":
        return cls(
            ece=float(m.get("ece", 0.0)),
            jsd=float(m.get("jsd", 0.0)),
            entropy=float(m.get("entropy", m.get("H", 0.0))),
            cv=float(m.get("cv", m.get("CV", 0.0))),
            gamma_temporal=float(m.get("gamma_temporal", 0.0)),
            gamma=float(m.get("gamma", 0.0)),
            impossible=bool(m.get("impossible", False)),
            notes=dict(m.get("notes", {})),
        )