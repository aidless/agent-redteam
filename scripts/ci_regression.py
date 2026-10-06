"""CI regression gate (v0.4 B3).

Runs the platform's smoke-test suites in sequence and compares each
suite's PASS count to a baseline. Default mode is **soft**: print
warning + exit 0 if any suite is below its baseline, so a fresh
check-in never breaks local dev on first introduction. Use
``--strict`` to make any regression exit 1.

Usage:
    # Soft (default) — print status, exit 0 unless a suite throws
    python scripts/ci_regression.py
    # Strict — fail build if any suite regresses
    python scripts/ci_regression.py --strict
    # Update the baseline to current PASS counts (maintainer use)
    python scripts/ci_regression.py --update-baseline

Output:
    Line-per-suite: ``suite_name: 17/17 PASS (baseline=17)`` then a
    summary line. ``--json`` prints machine-readable output for CI
    log scrapers.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"


# Baseline: minimum PASS count per suite. Maintained by
# ``--update-baseline``. If you intend to permanently drop a test,
# delete the suite here intentionally.
BASELINE: Dict[str, int] = {
    "test_targets.py":      9,    # v0.2 LLM target smoke tests
    "test_v03.py":         17,    # v0.3 six-task additions
    "test_v04.py":         10,    # v0.4 B1 pluggable embedders (10 incl. 1 skip-as-pass)
    "test_v04_storage.py": 11,    # v0.4 B2 SQLite storage
    "test_v04_b3.py":       9,    # v0.4 B3 CI gate + post-run calibration
    "test_v04_b4.py":       6,    # v0.4 B4 load_config + workflow + dashboard
    "test_v04_b6.py":              25,    # v0.4 B6 coverage sprint (factories + 7 aggregators + 4 attacks + Recorder + MultiAgent edges)
    "test_v04_b6_calib_history.py": 6,    # v0.4 B6 dashboard Historical Calibration tab (list/filter/limit + storage helpers)
}


PASS_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*tests?\s*passed", re.IGNORECASE)
RESULTS_LINE_RE = re.compile(r"Results:\s*(\d+)\s*passed,\s*(\d+)\s*failed", re.IGNORECASE)


def run_suite(suite: str, pyexe: str = sys.executable) -> Tuple[int, int, float]:
    """Run one suite, return (passed, total, wall_seconds)."""
    t0 = time.time()
    # Pass a recursion-guard env var so a suite that itself calls
    # ``ci_regression.evaluate()`` (e.g. test_v04_b3 D4) does NOT recursively
    # subprocess itself.
    import os as _os
    child_env = {**_os.environ, "_CI_REGRESSION_INVOKED_BY_SUITE": suite}
    proc = subprocess.run(
        [pyexe, str(TESTS_DIR / suite)],
        cwd=str(ROOT),
        capture_output=True, text=True,
        env=child_env,
    )
    elapsed = time.time() - t0
    out = proc.stdout + "\n" + proc.stderr

    # v0.2-style: "Results: N passed, M failed"
    m = RESULTS_LINE_RE.search(out)
    if m:
        return int(m.group(1)), int(m.group(1)) + int(m.group(2)), elapsed

    # v0.3+ style: "N/M tests passed"
    m = PASS_RE.search(out)
    if m:
        return int(m.group(1)), int(m.group(2)), elapsed

    # Fall back: assume zero on parse failure
    return 0, 0, elapsed


def evaluate(strict: bool) -> Tuple[List[dict], bool, List[str]]:
    """Run all suites + compare to baseline.

    Returns: (results, any_regression, warnings).

    Recursion guard: when called from inside a suite that is itself listed in
    BASELINE (e.g. ``tests/test_v04_b3.py`` runs ``ci_regression.evaluate()``
    which would otherwise recursively re-run the suite that triggered it),
    mark such suites as ``skipped_recursive`` rather than subprocess-running
    them. This prevents an infinite subprocess loop when this function is
    unit-tested under pytest.
    """
    results: List[dict] = []
    warnings: List[str] = []
    any_regression = False

    # Detect "am I currently being run as a test inside one of these suites?"
    import os as _os
    _current_suite = _os.environ.get("_CI_REGRESSION_INVOKED_BY_SUITE")
    if _current_suite and _current_suite in BASELINE:
        # Skip self-recursion: report as skipped, not a real pass/fail.
        results.append({
            "suite": _current_suite,
            "passed": BASELINE[_current_suite],
            "total": BASELINE[_current_suite],
            "baseline": BASELINE[_current_suite],
            "elapsed_seconds": 0.0,
            "regression": False,
            "parse_ok": True,
            "skipped_recursive": True,
        })
        warnings.append(f"{_current_suite}: skipped (recursive invocation guard)")
        return results, False, warnings

    for suite, baseline in BASELINE.items():
        if not (TESTS_DIR / suite).exists():
            # A vanished suite is a regression, not a skip. Treating it as a skip
            # meant deleting tests/test_v04_b6.py (25 cases) turned 93 tests into
            # 68 and the whole job stayed SUCCESS -- removing coverage made the
            # gate quieter. Fail closed instead.
            warnings.append(f"{suite}: MISSING test file - counted as regression")
            results.append({
                "suite": suite,
                "passed": 0,
                "total": baseline,
                "baseline": baseline,
                "elapsed_seconds": 0.0,
                "regression": True,
                "parse_ok": False,
                "missing": True,
            })
            any_regression = True
            continue
        # Recursion guard: if this suite is currently running this very
        # function, don't subprocess-run it again.
        if suite == _current_suite:
            results.append({
                "suite": suite,
                "passed": baseline,
                "total": baseline,
                "baseline": baseline,
                "elapsed_seconds": 0.0,
                "regression": False,
                "parse_ok": True,
                "skipped_recursive": True,
            })
            warnings.append(f"{suite}: skipped (recursive invocation guard)")
            continue
        passed, total, elapsed = run_suite(suite)
        regression = passed < baseline
        results.append({
            "suite": suite,
            "passed": passed,
            "total": total,
            "baseline": baseline,
            "elapsed_seconds": round(elapsed, 2),
            "regression": regression,
            "parse_ok": total > 0,
        })
        if regression:
            any_regression = True
            msg = f"{suite}: {passed}/{total} PASS — BELOW baseline {baseline}"
            warnings.append(msg)

    # Also: if any suite failed to parse, surface that
    parse_fail = [r for r in results if not r["parse_ok"]]
    if parse_fail:
        warnings.append(f"{len(parse_fail)} suite(s) unparseable — check runner output")

    # In strict mode, any unparseable suite counts as a regression
    if strict and parse_fail:
        any_regression = True

    return results, any_regression, warnings


def update_baseline(results: List[dict]) -> Dict[str, int]:
    """Write a new baseline dict from the current PASS counts."""
    new = {r["suite"]: r["passed"] for r in results if r["parse_ok"]}
    return new


def main() -> int:
    ap = argparse.ArgumentParser(description="CI regression gate (v0.4 B3)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--strict", action="store_true",
                   help="Exit 1 if any suite is below baseline (default: warn only).")
    g.add_argument("--soft", action="store_true",
                   help="Warn but always exit 0 (default; listed for explicitness).")
    ap.add_argument("--update-baseline", action="store_true",
                    help="Print updated baseline JSON to stdout (do not save).")
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON to stdout.")
    ns = ap.parse_args()

    results, any_regression, warnings = evaluate(strict=ns.strict)
    new_baseline = {r["suite"]: r["passed"] for r in results if r["parse_ok"]}

    if ns.json:
        print(json.dumps({
            "results": results,
            "baseline": dict(BASELINE),
            "new_baseline": new_baseline,
            "any_regression": any_regression,
            "warnings": warnings,
            "mode": "strict" if ns.strict else "soft",
        }, indent=2))
    else:
        print(f"=== CI regression gate ({'STRICT' if ns.strict else 'soft'}) ===")
        total_pass = sum(r["passed"] for r in results)
        total_baseline = sum(r["baseline"] for r in results)
        for r in results:
            tag = "OK " if not r["regression"] else "WARN"
            print(f"  [{tag}] {r['suite']:24s} {r['passed']:>3}/{r['total']:<3} "
                  f"(baseline={r['baseline']}, "
                  f"{r['elapsed_seconds']}s)")
        print(f"\n  Total: {total_pass}/{total_baseline} tests passing across "
              f"{len(results)} suites")
        if warnings:
            print(f"\n  Warnings ({len(warnings)}):")
            for w in warnings:
                print(f"    - {w}")

        if ns.update_baseline:
            print(f"\n=== Suggested new baseline (paste into BASELINE dict) ===")
            print(json.dumps(new_baseline, indent=2))

    if ns.update_baseline:
        # Update mode should not exit non-zero; user is just exploring.
        return 0

    if ns.strict and any_regression:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
