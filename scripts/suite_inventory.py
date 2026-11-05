"""Counts this repo actually has, derived from the tree.

The handwritten floors live in ``scripts/ci_regression.py``. This module
recomputes them from ``tests/test_*.py`` so a doc, a workflow list, or a
second copy of the floor cannot drift without a test failing.

Skips are not passes. Two skips are named and allowed:

* ``test_sentence_transformer_if_available`` — optional dependency
* ``test_d4_evaluate_regression_detection`` — only meaningful when the
  gate's recursion guard is set; the skip reason must say so
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
DEMO_TEST = ROOT / "demo" / "test_demo.py"

# suite -> {test name: substring that must appear in the skip reason}
ALLOWED_SKIPS: Dict[str, Dict[str, str]] = {
    "test_v04.py": {
        "test_sentence_transformer_if_available": "sentence-transformers",
    },
    "test_v04_b3.py": {
        "test_d4_evaluate_regression_detection": "recursion guard",
    },
}

INVENTORY_RE = re.compile(
    r"INVENTORY passed=(\d+) skipped=(\d+) failed=(\d+)"
)
SKIP_LINE_RE = re.compile(r"^\s*skip\s+(\S+?):\s*(.*)$", re.MULTILINE)
RESULTS_LINE_RE = re.compile(
    r"Results:\s*(\d+)\s*passed,\s*(\d+)\s*failed", re.IGNORECASE
)
PASS_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*tests?\s*passed", re.IGNORECASE)

# Files that mention these strings because they detect them.
PATH_SCAN_EXEMPT = {"demo/test_demo.py"}


def test_files() -> List[Path]:
    return sorted(TESTS_DIR.glob("test_*.py"))


def _function_names(path: Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                names.append(node.name)
    return names


def collected_by_suite() -> Dict[str, List[str]]:
    return {path.name: _function_names(path) for path in test_files()}


def demo_contract_tests() -> int:
    return len(_function_names(DEMO_TEST))


def floor_for(suite: str, collected: Mapping[str, List[str]]) -> int:
    return len(collected[suite]) - len(ALLOWED_SKIPS.get(suite, {}))


def floors(collected: Optional[Mapping[str, List[str]]] = None) -> Dict[str, int]:
    collected = collected or collected_by_suite()
    return {suite: floor_for(suite, collected) for suite in collected}


def facts() -> Dict[str, int]:
    collected = collected_by_suite()
    n = sum(len(v) for v in collected.values())
    allowed = sum(len(v) for v in ALLOWED_SKIPS.values())
    # Under pytest the recursion-guard skip does not fire. Only the
    # optional embedder test skips when sentence-transformers is absent.
    embedder_skips = 1 if any(
        "test_sentence_transformer_if_available" in names
        for names in collected.values()
    ) else 0
    return {
        "collected": n,
        "suites": len(collected),
        "pytest_passed_without_sentence_transformers": n - embedder_skips,
        "pytest_skipped_without_sentence_transformers": embedder_skips,
        "direct_runner_passes_under_gate": n - allowed,
        "direct_runner_skips_under_gate": allowed,
        "demo_contract_tests": demo_contract_tests(),
    }


def current_claims_text() -> str:
    """The only current counts. README and PROJECT_STATUS must contain this."""
    f = facts()
    return (
        "<!-- inventory\n"
        f"collected: {f['collected']}\n"
        f"suites: {f['suites']}\n"
        "pytest_passed_without_sentence_transformers: "
        f"{f['pytest_passed_without_sentence_transformers']}\n"
        "pytest_skipped_without_sentence_transformers: "
        f"{f['pytest_skipped_without_sentence_transformers']}\n"
        "direct_runner_passes_under_gate: "
        f"{f['direct_runner_passes_under_gate']}\n"
        "direct_runner_skips_under_gate: "
        f"{f['direct_runner_skips_under_gate']}\n"
        f"demo_contract_tests: {f['demo_contract_tests']}\n"
        "-->\n"
        "\n"
        "`pytest tests/` with sentence-transformers not installed collects "
        f"{f['collected']} tests: "
        f"{f['pytest_passed_without_sentence_transformers']} passed and "
        f"{f['pytest_skipped_without_sentence_transformers']} skipped. "
        "The skipped test is `test_sentence_transformer_if_available`.\n"
        "\n"
        "`python scripts/ci_regression.py --strict` on that same machine "
        f"reports {f['direct_runner_passes_under_gate']} passes and "
        f"{f['direct_runner_skips_under_gate']} skips across "
        f"{f['suites']} suites. The extra skip is "
        "`test_d4_evaluate_regression_detection`, which the gate's recursion "
        "guard skips and which is not counted as a pass.\n"
        "\n"
        "`python -m unittest demo/test_demo.py` is "
        f"{f['demo_contract_tests']} contract tests. It is not added into "
        "either count above.\n"
    )


def parse_direct_output(text: str) -> dict:
    """Parse a direct-runner transcript.

    An explicit ``INVENTORY`` line wins over a ``N/M tests passed`` line.
    The fraction line used to count skips as passes; preferring the
    inventory line is what stops that false green.
    """
    inv = INVENTORY_RE.search(text)
    skip_reasons = {m.group(1): m.group(2).strip() for m in SKIP_LINE_RE.finditer(text)}
    if inv:
        passed = int(inv.group(1))
        skipped = int(inv.group(2))
        failed = int(inv.group(3))
        return {
            "passed": passed,
            "skipped": skipped,
            "failed": failed,
            "total": passed + skipped + failed,
            "reasons": skip_reasons,
            "parse_ok": skipped == len(skip_reasons) or skipped == 0 and not skip_reasons,
        }
    m = RESULTS_LINE_RE.search(text)
    if m:
        passed, failed = int(m.group(1)), int(m.group(2))
        return {
            "passed": passed,
            "skipped": 0,
            "failed": failed,
            "total": passed + failed,
            "reasons": {},
            "parse_ok": True,
        }
    m = PASS_RE.search(text)
    if m:
        passed, total = int(m.group(1)), int(m.group(2))
        failed = max(0, total - passed)
        return {
            "passed": passed,
            "skipped": 0,
            "failed": failed,
            "total": total,
            "reasons": {},
            "parse_ok": True,
        }
    return {
        "passed": 0,
        "skipped": 0,
        "failed": 0,
        "total": 0,
        "reasons": {},
        "parse_ok": False,
    }


def unexpected_skips(suite: str, reasons: Mapping[str, str]) -> List[str]:
    allowed = ALLOWED_SKIPS.get(suite, {})
    bad: List[str] = []
    for name, reason in reasons.items():
        needle = allowed.get(name)
        if needle is None or needle not in reason:
            bad.append(name)
    return bad


def execute_direct(tests: List[tuple]) -> int:
    """Run callables the way the CI gate reads them. Skips are not passes."""
    passed = failed = skipped = 0
    skip_types = {"_Skip", "Skipped"}
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
        except BaseException as exc:
            if type(exc).__name__ in skip_types:
                skipped += 1
                print(f"  skip  {name}: {exc}")
                continue
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  ok    {name}")
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    print(
        f"INVENTORY passed={passed} skipped={skipped} failed={failed}"
    )
    return 0 if failed == 0 else 1


def author_path_hits(text: str) -> List[str]:
    """Return which author-machine path spellings appear in ``text``."""
    needles = ("F:" + "/", "F:" + "\\", "/" + "Users/", "C:" + "\\Users", "C:" + "/Users")
    return [needle for needle in needles if needle in text]
