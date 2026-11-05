"""Drift guards for the only current test counts.

These checks fail when a suite file, the CI floor, the workflow list, or the
README / PROJECT_STATUS inventory block disagree. They also fail if a direct
runner counts a skip as a pass, or if a failure hides behind the pass floor.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_BANNED_IN_CURRENT_CLAIMS = (
    "7 suites",
    "93/93",
    "86 passed",
    "61 passed",
    "92 passed",
)


def test_registered_suites_match_test_files():
    from scripts.ci_regression import BASELINE
    from scripts.suite_inventory import collected_by_suite

    assert set(BASELINE) == set(collected_by_suite())


def test_floor_is_collected_minus_allowed_skips():
    from scripts.ci_regression import BASELINE
    from scripts.suite_inventory import floors

    assert dict(BASELINE) == floors()


def test_workflow_lists_every_registered_suite():
    from scripts.ci_regression import BASELINE

    text = (ROOT / ".github" / "workflows" / "ci_multi_python.yml").read_text(
        encoding="utf-8"
    )
    match = re.search(r"for suite in (.+?); do", text, re.S)
    assert match, "suite loop not found in ci_multi_python.yml"
    listed = re.findall(r"tests/(test_[A-Za-z0-9_]+\.py)", match.group(1))
    assert set(listed) == set(BASELINE)
    assert len(listed) == len(set(listed))


def test_readme_and_status_inventory_match_tree():
    from scripts.suite_inventory import current_claims_text

    block = current_claims_text().strip()
    for rel in ("README.md", "PROJECT_STATUS.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        parts = text.split("<!-- current-claims: start -->", 1)
        assert len(parts) == 2, rel
        region = parts[1].split("<!-- current-claims: end -->", 1)[0]
        assert block in region, rel
        for banned in _BANNED_IN_CURRENT_CLAIMS:
            assert banned not in region, (rel, banned)


def test_allowed_skips_name_real_functions():
    from scripts.suite_inventory import ALLOWED_SKIPS, collected_by_suite

    collected = collected_by_suite()
    for suite, mapping in ALLOWED_SKIPS.items():
        for name in mapping:
            assert name in collected[suite], (suite, name)


def test_no_author_absolute_paths():
    from scripts.suite_inventory import PATH_SCAN_EXEMPT, author_path_hits

    listed = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True
    ).splitlines()
    hits = []
    for rel in listed:
        if rel in PATH_SCAN_EXEMPT:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = author_path_hits(text)
        if found:
            hits.append((rel, found))
    assert hits == []


def test_direct_runner_does_not_count_the_embedder_skip_as_a_pass():
    from scripts.suite_inventory import collected_by_suite, parse_direct_output

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "test_v04.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    parsed = parse_direct_output(proc.stdout + "\n" + proc.stderr)
    assert proc.returncode == 0, proc.stderr
    assert parsed["parse_ok"], parsed
    names = collected_by_suite()["test_v04.py"]
    installed = importlib.util.find_spec("sentence_transformers") is not None
    if installed:
        assert parsed["passed"] == len(names)
        assert parsed["skipped"] == 0
    else:
        assert parsed["passed"] == len(names) - 1
        assert parsed["skipped"] == 1
        assert parsed["failed"] == 0
        reason = parsed["reasons"]["test_sentence_transformer_if_available"]
        assert "sentence-transformers" in reason


def test_direct_runner_does_not_count_the_recursion_skip_as_a_pass():
    from scripts.suite_inventory import collected_by_suite, parse_direct_output

    env = dict(os.environ)
    env["_CI_REGRESSION_INVOKED_BY_SUITE"] = "test_v04_b3.py"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "test_v04_b3.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    parsed = parse_direct_output(proc.stdout + "\n" + proc.stderr)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert parsed["parse_ok"], parsed
    names = collected_by_suite()["test_v04_b3.py"]
    assert parsed["passed"] == len(names) - 1
    assert parsed["skipped"] == 1
    reason = parsed["reasons"]["test_d4_evaluate_regression_detection"]
    assert "recursion guard" in reason


def test_a_failure_is_a_regression_when_the_pass_floor_is_still_met():
    """A suite can meet the pass floor and still have a failed test.

    The old gate only checked ``passed < floor``, so that failure stayed green.
    """
    from scripts import ci_regression as cir

    saved = cir.run_suite
    previous = os.environ.pop("_CI_REGRESSION_INVOKED_BY_SUITE", None)

    def fake(suite, pyexe=None):
        floor = cir.BASELINE[suite]
        return (floor, floor + 1, 0.0, 0, {})

    try:
        cir.run_suite = fake
        _results, regress, warnings = cir.evaluate(strict=True)
    finally:
        cir.run_suite = saved
        if previous is not None:
            os.environ["_CI_REGRESSION_INVOKED_BY_SUITE"] = previous
    assert regress is True
    assert any("not covered by the pass floor" in w for w in warnings)


def test_inventory_parser_prefers_the_explicit_line():
    from scripts.suite_inventory import parse_direct_output

    text = (
        "10/10 tests passed\n"
        "  skip  test_sentence_transformer_if_available: "
        "sentence-transformers not installed\n"
        "INVENTORY passed=9 skipped=1 failed=0\n"
    )
    parsed = parse_direct_output(text)
    assert parsed["parse_ok"]
    assert parsed["passed"] == 9
    assert parsed["skipped"] == 1
    assert parsed["failed"] == 0
    assert parsed["total"] == 10


if __name__ == "__main__":
    from scripts.suite_inventory import execute_direct

    names = [name for name in globals() if name.startswith("test_")]
    # globals() during the loop below must not pick up names bound later.
    tests = [(name, globals()[name]) for name in names]
    sys.exit(execute_direct(tests))
