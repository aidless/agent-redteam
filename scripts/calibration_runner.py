"""Calibration runner (v0.4 B3 — bridges metrics/ to storage/).

Builds a synthetic "biased-vs-clean" verifier score stream (two
arrays of confidences in [0,1]), computes all six calibration
metrics from `metrics.calibration`, packages them into a
`CalibrationReport`, and (optionally) persists the report to the
platform SQLite DB via a supplied `Recorder`.

Why synthetic? The runner is the canonical entry point for turning
"drift between two calibration regimes" into a persisted report;
this matters in CI (D4) where we want to gate regressions even when
a real LLM target isn't available. With a deterministic
`random.Random(seed)`, the metrics are reproducible across runs.

Usage:
    from scripts.calibration_runner import run_calibration
    report = run_calibration(seed=42, n=200)
    # `report.notes["gamma_temporal_n"], report.notes["jsd_distribution_a_vs_b"]`

CLI:
    python scripts/calibration_runner.py --seed 42 --n 200 --record
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from metrics import (
    ece, jsd, entropy, cv, gamma_temporal, coupling, impossibility_triangle,
)
from metrics.calibration import CalibrationReport


def synth_score_stream(
    n: int,
    seed: int = 42,
    bias: float = 0.25,
) -> tuple:
    """Generate two synthetic verifier confidence streams.

    `biased`  : a stream shifted by `bias` (simulates verifier
                over-confidence under attack-pressure)
    `clean`   : the baseline stream
    `labels_a`: hard labels for `biased` (mostly `>= 0.5` => 1)
    `labels_b`: hard labels for `clean`

    Returns 4-tuple (biased, clean, labels_a, labels_b).
    """
    rng = random.Random(seed)
    clean = [rng.random() for _ in range(n)]
    biased = [min(1.0, max(0.0, c + rng.gauss(bias, 0.10))) for c in clean]
    # Labels derived from clean ground truth with probability
    labels_a = [1 if rng.random() < c else 0 for c in clean]
    labels_b = list(labels_a)
    return biased, clean, labels_a, labels_b


def run_calibration(
    seed: int = 42,
    n: int = 200,
    bias: float = 0.25,
) -> CalibrationReport:
    """Run all six metrics on a seeded synthetic stream.

    Returns a `CalibrationReport` with `notes` populated with the
    raw inputs (for forensics in the Historical Runs tab).
    """
    biased, clean, labels_a, labels_b = synth_score_stream(
        n=n, seed=seed, bias=bias,
    )
    # ECE: use biased stream
    ece_val = ece(biased, labels_a, n_bins=15)
    # JSD: distribution (binned) of biased vs clean (10 bins, [0, 1])
    def hist(stream, bins=10):
        h = [0.0] * bins
        for v in stream:
            idx = min(bins - 1, int(v * bins))
            h[idx] += 1
        total = sum(h) or 1.0
        return [x / total for x in h]
    jsd_val = jsd(hist(biased), hist(clean))
    # H: entropy of the biased distribution histogram
    h_val = entropy(hist(biased))
    # CV: coefficient of variation of biased scores
    cv_val = cv(biased)
    # γ_temporal: Wasserstein-1 between biased and clean
    gtmp_val = gamma_temporal(biased, clean)
    # γ coupling: between (treating biased as W_TV, clean as W_V)
    gcoup_val = coupling(biased, clean)
    # impossibility triangle (γ_temporal · H · CV ≥ c_min)
    ir = impossibility_triangle(
        gamma=gtmp_val, H=h_val, CV=cv_val,
        c_min=1e-3,
    )
    report = CalibrationReport(
        ece=ece_val, jsd=jsd_val, entropy=h_val, cv=cv_val,
        gamma_temporal=gtmp_val, gamma=gcoup_val,
        impossible=bool(ir.violated),
        notes={
            "seed": seed, "n": n, "bias": bias,
            "biased_mean": round(statistics.fmean(biased), 6),
            "clean_mean": round(statistics.fmean(clean), 6),
            "biased_stdev": round(statistics.pstdev(biased), 6),
            "product_gamma_H_CV": round(float(ir.product), 6),
            "c_min": float(ir.c_min),
            "source": "calibration_runner.run_calibration",
        },
    )
    return report


def run_calibration_recorded(
    seed: int = 42,
    n: int = 200,
    bias: float = 0.25,
    recorder: object = None,
    source_tag: str = "calibration_runner",
) -> CalibrationReport:
    """Wrap `run_calibration` and persist the report via `recorder`."""
    report = run_calibration(seed=seed, n=n, bias=bias)
    if recorder is not None:
        try:
            recorder.record_calibration(source_tag, report)
        except Exception as e:
            print(f"[warn] record_calibration failed: {e!r}")
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Calibration runner (v0.4 B3)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--bias", type=float, default=0.25)
    ap.add_argument("--record", action="store_true",
                    help="Persist the report to storage/agent_redteam.db")
    ns = ap.parse_args()

    rec = None
    if ns.record:
        try:
            from storage import Recorder
            rec = Recorder(mode="calibration",
                           target_provider="synthetic",
                           target_model=f"seed-{ns.seed}-n-{ns.n}-bias-{ns.bias}",
                           rounds=ns.n,
                           config_yaml=None)
            rec.__enter__()
        except Exception as e:
            print(f"[warn] recorder init failed: {e!r}")
            rec = None
    try:
        rpt = run_calibration_recorded(seed=ns.seed, n=ns.n, bias=ns.bias,
                                       recorder=rec,
                                       source_tag="cli_calibration_runner")
    finally:
        if rec is not None:
            try:
                rec.finalize()
                rec.__exit__(None, None, None)
            except Exception as e:
                print(f"[warn] finalize failed: {e!r}")

    print(f"=== Calibration report (seed={ns.seed}, n={ns.n}, bias={ns.bias}) ===")
    for k, v in rpt.to_dict().items():
        if k == "notes":
            print(f"  notes: {v}")
        else:
            print(f"  {k}: {v}")
