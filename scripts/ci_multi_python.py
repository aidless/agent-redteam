#!/usr/bin/env python3
"""CI multi-Python matrix runner (v0.4 B6).

Runs the Agent Red Team test suite against multiple Python interpreters
to catch forward-compat issues (3.12+ PEP 695 generic aliases, 3.11+
ExceptionGroups, etc.) before they bite a fresh contributor.

Default matrix: 3.10 / 3.11 / 3.12 (the project's stated support window).
Any interpreter not on PATH is silently skipped (logged), never failed.

Usage
-----
    python scripts/ci_multi_python.py                # full matrix
    python scripts/ci_multi_python.py --py 3.12     # single Python
    python scripts/ci_multi_python.py --quick       # only the b3+b4+b6 smoke tests
    python scripts/ci_multi_python.py --json        # machine-readable

Exit code
---------
0  - every available Python passed (>= baseline per suite)
1  - at least one Python regressed OR we hit a hard setup error
2  - no usable Python found
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
REQUIREMENTS = ROOT / "requirements.txt"

# Default matrix — mirrors the project's stated support window.
# Each entry: (label, binary-name, bare-minimum-version).
DEFAULT_MATRIX: List[Tuple[str, str, str]] = [
    ("3.10", "python3.10", "3.10"),
    ("3.11", "python3.11", "3.11"),
    ("3.12", "python3.12", "3.12"),
]

# Suites considered "smoke" for --quick mode.  Anything not in this
# list is omitted when --quick is passed.
QUICK_SUITES = (
    "test_v04_b3.py",
    "test_v04_b4.py",
    "test_v04_b6.py",
    "test_v04_b6_calib_history.py",
)

# Mirror of the baseline in scripts/ci_regression.py (kept duplicated
# here so ci_multi_python can run independently — does not import
# ci_regression to avoid a circular invocation risk).
BASELINE: Dict[str, int] = {
    "test_targets.py":                9,
    "test_v03.py":                   17,
    "test_v04.py":                   10,
    "test_v04_storage.py":           11,
    "test_v04_b3.py":                 9,
    "test_v04_b4.py":                 6,
    "test_v04_b6.py":                25,
    "test_v04_b6_calib_history.py":   6,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_python(bin_name: str) -> Optional[str]:
    """Resolve `bin_name` to an absolute path, or None if missing.

    Tries (in order):
    1. shutil.which(bin_name)
    2. uv-managed Python via `uv python find <version>`
    """
    p = shutil.which(bin_name)
    if p:
        return p
    # uv fallback — extract "3.10" from "python3.10"
    ver = bin_name.replace("python", "")
    try:
        out = subprocess.run(
            ["uv", "python", "find", ver],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def version_of(pyexe: str) -> Optional[Tuple[int, int]]:
    """Return (major, minor) for the given interpreter."""
    try:
        out = subprocess.run(
            [pyexe, "-c", "import sys; print(sys.version_info.major, sys.version_info.minor)"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode == 0:
            parts = out.stdout.strip().split()
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None


def run_one(pyexe: str, suites: List[str], venv_dir: Path) -> Dict:
    """Bootstrap a venv with `pyexe` and run the requested suites.

    Returns a per-Python result dict: {pyexe, version, venv, results,
    elapsed_seconds, error}.
    """
    t0 = time.time()
    res: Dict = {
        "pyexe": pyexe,
        "version": None,
        "venv": str(venv_dir),
        "results": [],
        "elapsed_seconds": 0.0,
        "error": None,
    }
    ver = version_of(pyexe)
    if ver is None:
        res["error"] = "could not determine Python version"
        res["elapsed_seconds"] = round(time.time() - t0, 2)
        return res
    res["version"] = f"{ver[0]}.{ver[1]}"

    # 1) Create venv
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
    venv_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [{res['version']}] creating venv at {venv_dir} ...", file=sys.stderr,
          flush=True)
    try:
        subprocess.run(
            [pyexe, "-m", "venv", str(venv_dir)],
            check=True, timeout=120, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        res["error"] = f"venv create failed: {e.stderr.decode(errors='replace')[:200]}"
        res["elapsed_seconds"] = round(time.time() - t0, 2)
        return res

    py_in_venv = venv_dir / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    if not py_in_venv.exists():
        # Some uv-created venvs on Windows put the binary at `Scripts/python`
        # (no .exe suffix); check that as a fallback before giving up.
        fallback = venv_dir / ("Scripts" if os.name == "nt" else "bin") / "python"
        if fallback.exists():
            py_in_venv = fallback
        else:
            res["error"] = f"venv python missing at {py_in_venv}"
            res["elapsed_seconds"] = round(time.time() - t0, 2)
            return res

    # 2) pip install requirements — best effort; tolerate failure (e.g.
    #    some packages may not have wheels for the old Python).
    pip_args = [str(py_in_venv), "-m", "pip", "install",
                "--disable-pip-version-check"]
    if REQUIREMENTS.exists():
        pip_args += ["-r", str(REQUIREMENTS)]
    pip_args += ["pytest"]  # always need pytest for tests/
    print(f"  [{res['version']}] pip install (this may take 1-2 min) ...",
          file=sys.stderr, flush=True)
    try:
        proc = subprocess.run(
            pip_args, capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            res["error"] = (
                f"pip install failed (rc={proc.returncode}): "
                f"{proc.stderr[-300:]}"
            )
            res["elapsed_seconds"] = round(time.time() - t0, 2)
            return res
    except subprocess.TimeoutExpired:
        res["error"] = "pip install timeout (>600s)"
        res["elapsed_seconds"] = round(time.time() - t0, 2)
        return res

    # 3) Run each suite via its direct runner (more portable than pytest
    #    across interpreters; matches ci_regression's suite-by-suite
    #    invocation).
    for suite in suites:
        suite_path = TESTS_DIR / suite
        if not suite_path.exists():
            res["results"].append({
                "suite": suite, "passed": 0, "total": 0,
                "baseline": BASELINE.get(suite, 0),
                "elapsed_seconds": 0.0, "regression": True,
                "skipped_missing": True,
            })
            continue
        ts = time.time()
        print(f"  [{res['version']}] running {suite} ...", file=sys.stderr,
              flush=True)
        proc = subprocess.run(
            [str(py_in_venv), "-u", str(suite_path)],
            capture_output=True, text=True, timeout=300,
            cwd=str(ROOT),
        )
        elapsed = round(time.time() - ts, 2)
        passed, total = _parse_runner_output(proc.stdout + proc.stderr)
        baseline = BASELINE.get(suite, 0)
        res["results"].append({
            "suite": suite,
            "passed": passed,
            "total": total,
            "baseline": baseline,
            "elapsed_seconds": elapsed,
            "regression": passed < baseline,
            "exit_code": proc.returncode,
        })

    res["elapsed_seconds"] = round(time.time() - t0, 2)
    return res


def _parse_runner_output(text: str) -> Tuple[int, int]:
    """Parse '<passed>/<total> tests passed' from runner stdout.

    Falls back to (0, 0) if not found — caller treats that as parse fail.
    """
    import re
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*tests?\s*passed", text, re.IGNORECASE)
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2))


def emit_markdown(rows: List[Dict]) -> str:
    """Render the multi-Python matrix as a Markdown table."""
    lines = ["## Multi-Python matrix\n"]
    header = "| Python | Suite | Passed | Baseline | Regress | Seconds |"
    sep = "|--------|-------|--------|----------|---------|---------|"
    lines += [header, sep]
    for r in rows:
        ver = r.get("version") or "?"
        err = r.get("error")
        if err:
            lines.append(f"| **{ver}** | _all suites_ | _setup error_ | — | — | — |")
            lines.append(f"|  | {err} |  |  |  |  |")
            continue
        for s in r["results"]:
            tag = "❌" if s.get("regression") or s.get("skipped_missing") else "✅"
            lines.append(
                f"| **{ver}** | `{s['suite']}` | "
                f"{s['passed']}/{s['total']} | {s['baseline']} | "
                f"{tag} | {s['elapsed_seconds']}s |"
            )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--py", action="append", default=[],
                    help="Restrict to specific Python label(s) (repeatable)")
    ap.add_argument("--quick", action="store_true",
                    help="Run only quick smoke suites (B3 + B4 + B6)")
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON to stdout")
    ap.add_argument("--keep-venv", action="store_true",
                    help="Keep temp venvs (default: clean up)")
    args = ap.parse_args()

    matrix = DEFAULT_MATRIX
    if args.py:
        wanted = set(args.py)
        matrix = [(lbl, bin_, v) for (lbl, bin_, v) in matrix if lbl in wanted]

    suites = [s for s in BASELINE if (TESTS_DIR / s).exists()]
    if args.quick:
        suites = [s for s in suites if s in QUICK_SUITES]

    rows: List[Dict] = []
    any_regression = False
    usable = 0

    for lbl, bin_name, _ in matrix:
        pyexe = find_python(bin_name)
        if pyexe is None:
            rows.append({"version": lbl, "error": f"{bin_name} not on PATH (skipped)"})
            continue
        usable += 1
        with tempfile.TemporaryDirectory(prefix=f"art-py{lbl}-") as vtmp:
            venv_dir = Path(vtmp) / "venv"
            r = run_one(pyexe, suites, venv_dir)
            if args.keep_venv:
                print(f"[info] venv kept at {venv_dir} for python {lbl}", file=sys.stderr)
            rows.append(r)
            for s in r.get("results", []):
                if s.get("regression") or s.get("skipped_missing"):
                    any_regression = True

    if args.json:
        print(json.dumps({"matrix": rows, "any_regression": any_regression,
                          "usable": usable}, indent=2))
    else:
        print(emit_markdown(rows))
        print(f"Total usable Pythons: {usable}")
        if any_regression:
            print("STATUS: ❌ regression detected")
        elif usable == 0:
            print("STATUS: ⚠️  no usable Python found")
        else:
            print("STATUS: ✅ all matrices green")

    if usable == 0:
        return 2
    return 1 if any_regression else 0


if __name__ == "__main__":
    sys.exit(main())