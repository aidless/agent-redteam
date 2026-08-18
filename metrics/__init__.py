"""Calibration metrics for multi-agent LLM systems (survey §2.2).

Implements the six metrics used across [P1]-[P6]:
- ECE (Expected Calibration Error, 15 bins)
- JSD (Jensen-Shannon Divergence)
- H  (Shannon entropy in [0, 1])
- CV (coefficient of variation = std/mean)
- gamma_temporal (Wasserstein-1 distance between two distributions)
- gamma (coupling coefficient: ||W_{T->V} - W_V||_2 / ||W_V||_2)
- impossibility_triangle (gamma * H * CV >= c_min)

All functions are pure-Python with stdlib `math` only — no numpy —
so they can be unit-tested without heavy deps and shipped with the
Agent Red Team Platform as a small library.

Design notes (mirrors survey §2.2 / §4.1):
- `ece` uses equal-width bins in [0, 1], n_bins default 15 (per [P4]).
- `entropy` is normalized by log2(n) so it lands in [0, 1].
- `cv` returns +inf when mean is exactly 0; this matches pandas/std defs.
- `gamma_temporal` is a 1-D Wasserstein-1 over sorted CDFs.
- `coupling` follows the L2-norm definition used in [P2].
- `impossibility_triangle` returns (violated: bool, product: float, c_min: float).
"""

from .calibration import (
    ece,
    jsd,
    entropy,
    cv,
    gamma_temporal,
    coupling,
    impossibility_triangle,
    CalibrationReport,
)

__all__ = [
    "ece",
    "jsd",
    "entropy",
    "cv",
    "gamma_temporal",
    "coupling",
    "impossibility_triangle",
    "CalibrationReport",
]