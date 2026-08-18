"""v0.4 B6 tests: calibration-history storage helpers + dashboard tab wiring.

6 tests:
- list_calibration_reports() returns rows joined with runs (started_at etc.)
- list_calibration_reports(source=...) filter (str + list + empty list)
- list_calibration_reports(limit=N) cap
- count_calibration_reports_by_source() groups correctly
- CALIBRATION_SOURCE_TAGS contains the canonical tags used by the runner
- dashboard.py imports & refers to all 5 tabs incl. new "Calibration History"
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _make_calib_row(db_path: str, *, run_id: int, source: str,
                    ece: float, jsd: float, gamma: float, impossible: int):
    """Insert one calibration_reports row tied to an existing run row."""
    from storage.db import connect, init_schema
    conn = connect(db_path)
    try:
        init_schema(conn)
        conn.execute(
            "INSERT INTO calibration_reports "
            "(run_id, source, ece, jsd, entropy, cv, "
            " gamma_temporal, gamma, impossible) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(run_id), str(source),
             float(ece), float(jsd), 0.5, 0.5, 0.1, float(gamma), int(impossible)),
        )
    finally:
        conn.close()


def _make_run_row(db_path: str, *, mode: str = "calibration") -> int:
    """Insert a run row and return its id."""
    from storage.db import connect, init_schema
    conn = connect(db_path)
    try:
        init_schema(conn)
        cur = conn.execute(
            "INSERT INTO runs (mode, target_provider, target_model, rounds) "
            "VALUES (?, ?, ?, ?)",
            (mode, "mock", "mock-model-v1", 1),
        )
        return int(cur.lastrowid)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ch1_list_calibration_reports_returns_rows_with_run_fields():
    """list_calibration_reports() rows must include both calibration
    columns and run-context columns (started_at, mode, target_*)."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        rid = _make_run_row(db)
        _make_calib_row(db, run_id=rid, source="dashboard_run",
                        ece=0.1, jsd=0.2, gamma=0.3, impossible=0)

        from storage import list_calibration_reports
        rows = list_calibration_reports(db_path=db)
        assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
        r = rows[0]
        for k in ("run_id", "source", "ece", "jsd", "entropy", "cv",
                  "gamma_temporal", "gamma", "impossible",
                  "started_at", "mode", "target_provider", "target_model"):
            assert k in r, f"missing key {k!r} in row"
        assert r["source"] == "dashboard_run"
        assert abs(r["ece"] - 0.1) < 1e-9
        assert r["impossible"] is False
    print("  ok    test_ch1_list_calibration_reports_returns_rows_with_run_fields")


def test_ch2_list_calibration_reports_filters_by_source_str_and_list():
    """source=str | source=[..] | source=[] must all be respected."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        for tag in ("dashboard_run", "cli_calibration_runner", "post_run_multi"):
            rid = _make_run_row(db)
            _make_calib_row(db, run_id=rid, source=tag,
                            ece=0.0, jsd=0.0, gamma=0.0, impossible=0)

        from storage import list_calibration_reports

        # str filter
        only_cli = list_calibration_reports(source="cli_calibration_runner", db_path=db)
        assert len(only_cli) == 1
        assert only_cli[0]["source"] == "cli_calibration_runner"

        # list filter
        multi = list_calibration_reports(
            source=["dashboard_run", "post_run_multi"], db_path=db,
        )
        assert len(multi) == 2
        assert {r["source"] for r in multi} == {"dashboard_run", "post_run_multi"}

        # empty list filter → no rows (not "no filter")
        empty = list_calibration_reports(source=[], db_path=db)
        assert empty == []

        # None filter → all rows
        all_rows = list_calibration_reports(source=None, db_path=db)
        assert len(all_rows) == 3
    print("  ok    test_ch2_list_calibration_reports_filters_by_source_str_and_list")


def test_ch3_list_calibration_reports_respects_limit():
    """limit=N caps the returned row count."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        for _ in range(5):
            rid = _make_run_row(db)
            _make_calib_row(db, run_id=rid, source="post_run_multi",
                            ece=0.0, jsd=0.0, gamma=0.0, impossible=0)

        from storage import list_calibration_reports
        rows = list_calibration_reports(limit=2, db_path=db)
        assert len(rows) == 2, f"limit=2 should clamp to 2, got {len(rows)}"
    print("  ok    test_ch3_list_calibration_reports_respects_limit")


def test_ch4_count_calibration_reports_by_source_groups():
    """count_calibration_reports_by_source() returns {source: int}."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        # 2 dashboard_run + 3 post_run_multi + 1 cli_calibration_runner
        for _ in range(2):
            rid = _make_run_row(db)
            _make_calib_row(db, run_id=rid, source="dashboard_run",
                            ece=0, jsd=0, gamma=0, impossible=0)
        for _ in range(3):
            rid = _make_run_row(db)
            _make_calib_row(db, run_id=rid, source="post_run_multi",
                            ece=0, jsd=0, gamma=0, impossible=0)
        rid = _make_run_row(db)
        _make_calib_row(db, run_id=rid, source="cli_calibration_runner",
                        ece=0, jsd=0, gamma=0, impossible=0)

        from storage import count_calibration_reports_by_source
        counts = count_calibration_reports_by_source(db_path=db)
        assert counts == {
            "post_run_multi": 3,
            "dashboard_run": 2,
            "cli_calibration_runner": 1,
        }, f"unexpected counts: {counts}"
    print("  ok    test_ch4_count_calibration_reports_by_source_groups")


def test_ch5_calibration_source_tags_contains_canonical_tags():
    """CALIBRATION_SOURCE_TAGS must include the tags the runners emit."""
    from storage import CALIBRATION_SOURCE_TAGS
    # Tags emitted by scripts/calibration_runner.py and dashboard tab_calib.
    required = {"calibration_runner", "cli_calibration_runner",
                "dashboard_run", "post_run_multi"}
    have = set(CALIBRATION_SOURCE_TAGS)
    missing = required - have
    assert not missing, f"missing canonical tags: {missing}"
    # Make sure it's a tuple (immutable) — used as default in dashboard filter
    assert isinstance(CALIBRATION_SOURCE_TAGS, tuple)
    print("  ok    test_ch5_calibration_source_tags_contains_canonical_tags")


def test_ch6_dashboard_has_calibration_history_tab():
    """scripts/dashboard.py must define a 5th tab "Calibration History"
    and reference list_calibration_reports / count_calibration_reports_by_source."""
    dash_path = ROOT / "scripts" / "dashboard.py"
    src = dash_path.read_text(encoding="utf-8")

    # 1) The new tab label exists in st.tabs([...]).
    assert "Calibration History" in src, \
        "dashboard.py missing 'Calibration History' tab label"

    # 2) Both storage helpers are imported inside the tab.
    assert "list_calibration_reports" in src, \
        "dashboard.py missing import of list_calibration_reports"
    assert "count_calibration_reports_by_source" in src, \
        "dashboard.py missing import of count_calibration_reports_by_source"

    # 3) The tab body block exists.
    assert "with tab_calib_history:" in src, \
        "dashboard.py missing `with tab_calib_history:` block"
    print("  ok    test_ch6_dashboard_has_calibration_history_tab")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_ch1_list_calibration_reports_returns_rows_with_run_fields,
        test_ch2_list_calibration_reports_filters_by_source_str_and_list,
        test_ch3_list_calibration_reports_respects_limit,
        test_ch4_count_calibration_reports_by_source_groups,
        test_ch5_calibration_source_tags_contains_canonical_tags,
        test_ch6_dashboard_has_calibration_history_tab,
    ]
    passed = failed = 0
    SKIP_TYPES = ("_Skip", "Skipped")
    for t in tests:
        try:
            t()
            passed += 1
        except BaseException as e:
            if type(e).__name__ in SKIP_TYPES:
                passed += 1
                print(f"  skip  {t.__name__}: {e}")
                continue
            print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed")
    sys.exit(0 if failed == 0 else 1)