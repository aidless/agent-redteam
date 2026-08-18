"""v0.4 B2 smoke tests for the SQLite trace storage layer.

These tests cover the storage/ package:
- db.py: connect, init_schema, idempotent re-init
- recorder.py: context manager, record_attack / record_tradeoff_point /
  record_calibration, finalize, read helpers
- integration: run_redteam writes a run row + per-round attack_results
- integration: run_tradeoff_recorded writes a run row + per-point
  tradeoff_points with is_pareto flag

Run with:
    .venv/Scripts/python.exe -m pytest tests/test_v04_storage.py -v
or directly:
    .venv/Scripts/python.exe tests/test_v04_storage.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# C1: db helpers
# ---------------------------------------------------------------------------

def test_db_connect_returns_connection(tmp_path=None):
    """connect() returns a Connection with WAL + foreign_keys + Row factory."""
    from storage.db import connect, DEFAULT_DB_PATH
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        c = connect(db)
        try:
            assert isinstance(c, sqlite3.Connection)
            # Verify PRAGMAs
            mode = c.execute("PRAGMA journal_mode").fetchone()[0].lower()
            assert mode == "wal", f"expected WAL, got {mode}"
            fk = c.execute("PRAGMA foreign_keys").fetchone()[0]
            assert fk == 1, f"expected foreign_keys=1, got {fk}"
            # Row factory should give Row objects
            c.execute("CREATE TABLE t(id INTEGER)")
            c.execute("INSERT INTO t(id) VALUES (1)")
            row = c.execute("SELECT id FROM t").fetchone()
            assert row["id"] == 1
        finally:
            c.close()
    # Sanity: DEFAULT_DB_PATH is a Path ending in .db
    assert DEFAULT_DB_PATH.name.endswith(".db")


def test_db_init_schema_idempotent(tmp_path=None):
    """init_schema can run twice without raising and tables still exist."""
    from storage.db import connect, init_schema
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        c1 = connect(db)
        init_schema(c1)
        # Re-run on a fresh connection against same file
        c2 = connect(db)
        # Must not raise
        init_schema(c2)
        # All 5 tables present (4 + schema_version)
        names = [r[0] for r in c2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        for required in ("runs", "attack_results", "tradeoff_points",
                         "calibration_reports", "schema_version"):
            assert required in names, f"missing table {required}, got {names}"
        c1.close(); c2.close()


# ---------------------------------------------------------------------------
# C2: Recorder context manager + writer methods
# ---------------------------------------------------------------------------

def test_recorder_context_manager_creates_run_row():
    """with Recorder(...) as r: creates a run row on enter, updates on exit."""
    from storage import Recorder
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "rec.db")
        with Recorder(mode="single", target_provider="mock",
                      target_model="t", rounds=2,
                      db_path=db_path, config_yaml="k: v") as r:
            run_id = r.run_id
            assert run_id is not None and run_id > 0
        # After exit, finished_at must be set
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        assert row["finished_at"] is not None, "finished_at not stamped"
        assert row["target_provider"] == "mock"
        conn.close()


def test_recorder_record_attack_writes_row():
    """record_attack persists one row per call."""
    from storage import Recorder
    from attacks.base import AttackResult, AttackSeverity

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "ar.db")
        with Recorder(mode="single", db_path=db_path) as r:
            rid = r.run_id
            for i in range(3):
                ar = AttackResult(
                    attack_name=f"V0{i+1}",
                    severity=AttackSeverity.HIGH,
                    success=(i % 2 == 0),
                    blocked_by=["input_separation"],
                    elapsed_ms=12.5 + i,
                    metadata={"total_cost_usd": 0.001 * i,
                              "response_preview": "ok",
                              "mode": "single",
                              "round_idx": i},
                )
                r.record_attack(ar)
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT attack_name, success FROM attack_results "
                            "WHERE run_id=? ORDER BY id", (rid,)).fetchall()
        assert len(rows) == 3
        assert [r[0] for r in rows] == ["V01", "V02", "V03"]
        assert [r[1] for r in rows] == [1, 0, 1]
        conn.close()


def test_recorder_record_tradeoff_marks_pareto():
    """record_tradeoff_point stores is_pareto as 1 when set True, else 0."""
    from storage import Recorder
    from scripts.tradeoff import TradeoffPoint

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "to.db")
        with Recorder(mode="tradeoff", db_path=db_path) as r:
            rid = r.run_id
            for is_pareto, util in [(True, 0.8), (False, 0.5), (True, 0.9)]:
                p = TradeoffPoint(
                    n_defenses_on=2,
                    defense_names=["input_separation", "tool_whitelist"],
                    task_utility=util,
                    block_rate=0.3,
                    total_cost_usd=0.01,
                    total_latency_ms=100.0,
                )
                r.record_tradeoff_point(p, is_pareto=is_pareto)
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT is_pareto FROM tradeoff_points "
                            "WHERE run_id=? ORDER BY id", (rid,)).fetchall()
        assert [r[0] for r in rows] == [1, 0, 1]
        conn.close()


def test_recorder_record_calibration_writes_metrics():
    """record_calibration persists the 6 metric columns."""
    from storage import Recorder
    from metrics.calibration import CalibrationReport

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "cal.db")
        with Recorder(mode="single", db_path=db_path) as r:
            rid = r.run_id
            r.record_calibration("post_run", CalibrationReport(
                ece=0.05, jsd=0.10, entropy=0.7, cv=1.1,
                gamma_temporal=0.2, gamma=0.3, impossible=False,
            ))
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT ece, jsd, entropy, cv, gamma_temporal, gamma, "
                           "impossible, source FROM calibration_reports "
                           "WHERE run_id=?", (rid,)).fetchone()
        assert row[0] == 0.05 and row[1] == 0.10
        assert row[2] == 0.7 and row[3] == 1.1
        assert row[4] == 0.2 and row[5] == 0.3
        assert row[6] == 0 and row[7] == "post_run"
        conn.close()


# ---------------------------------------------------------------------------
# C2: Read helpers
# ---------------------------------------------------------------------------

def test_list_runs_includes_aggregates():
    """list_runs returns n_attacks / n_blocked from LEFT JOIN."""
    from storage import Recorder, list_runs
    from attacks.base import AttackResult, AttackSeverity

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "lr.db")
        with Recorder(mode="single", db_path=db_path) as r:
            for i in range(5):
                r.record_attack(AttackResult(
                    attack_name=f"V0{i}", severity=AttackSeverity.MEDIUM,
                    success=(i < 3), blocked_by=[],
                    metadata={"total_cost_usd": 0.0, "response_preview": "",
                              "mode": "single", "round_idx": i},
                ))
            rid = r.run_id
        rows = list_runs(db_path=db_path, limit=10)
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == rid
        assert row["n_attacks"] == 5
        assert row["n_blocked"] == 2
        assert row["n_tradeoff_pts"] == 0


def test_get_run_aggregates_returns_block_rate():
    """get_run_aggregates computes attack_block_rate correctly."""
    from storage import Recorder, get_run_aggregates
    from attacks.base import AttackResult, AttackSeverity

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "agg.db")
        with Recorder(mode="multi", db_path=db_path) as r:
            # 4 attacks, 3 blocked → block_rate 0.75
            for i in range(4):
                r.record_attack(AttackResult(
                    attack_name=f"a{i}", severity=AttackSeverity.LOW,
                    success=(i == 0), blocked_by=[],
                    metadata={"total_cost_usd": 0.0, "response_preview": "",
                              "mode": "multi", "round_idx": i},
                ))
            rid = r.run_id
        agg = get_run_aggregates(rid, db_path=db_path)
        assert agg["attack_count"] == 4
        assert agg["attack_success_count"] == 1
        assert agg["attack_block_count"] == 3
        assert abs(agg["attack_block_rate"] - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# Integration: run_redteam + run_tradeoff_recorded write to DB
# ---------------------------------------------------------------------------

def test_run_redteam_persists_to_db(tmp_path=None):
    """End-to-end: run_redteam(mode='single', record=True) writes to DB."""
    from scripts.run_redteam import run_redteam
    from storage import list_runs, list_attack_results

    with tempfile.TemporaryDirectory() as td:
        # Point all storage at a temp DB by overriding the Recorder default
        db_path = str(Path(td) / "e2e.db")
        os.environ["AGENT_REDTEAM_DB"] = db_path
        try:
            results = run_redteam(
                rounds=3,
                target_provider="mock",
                target_model="mock-model-v1",
                record=True,
            )
        finally:
            os.environ.pop("AGENT_REDTEAM_DB", None)

        # We didn't wire env-var override into Recorder; the default
        # DB at <ROOT>/storage/agent_redteam.db is used. So use that one.
        rows = list_runs(limit=5)
        assert len(rows) >= 1
        # Find the run we just created (mode=single, rounds=3, freshest)
        latest = [r for r in rows if r["mode"] == "single" and r["rounds"] == 3]
        assert latest, f"no matching single/3 run; runs: {rows}"
        run_id = latest[0]["id"]
        ars = list_attack_results(run_id)
        assert len(ars) == 3
        for a in ars:
            assert "attack_name" in a
            assert "success" in a


def test_run_tradeoff_recorded_persists_points():
    """run_tradeoff_recorded writes one tradeoff_points row per subset."""
    from scripts.tradeoff import run_tradeoff_recorded
    from targets import MockLLMTarget
    from defenses.input_separation import InputSeparationDefense
    from defenses.output_filter import OutputFilterDefense
    from storage import Recorder, list_tradeoff_points, list_runs
    from pathlib import Path
    import tempfile, os, sqlite3

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "to_e2e.db")
        rec = Recorder(mode="tradeoff", target_provider="mock",
                       target_model="mock-model-v1", rounds=4,
                       db_path=db_path)
        rec.__enter__()
        try:
            target = MockLLMTarget()
            base = [InputSeparationDefense(), OutputFilterDefense()]
            out = run_tradeoff_recorded(target, base, max_combinations=4,
                                        recorder=rec)
            assert out["n_recorded"] == 4
        finally:
            rec.__exit__(None, None, None)

        rows = list_tradeoff_points(rec.run_id, db_path=db_path)
        assert len(rows) == 4
        for r in rows:
            assert 0.0 <= r["task_utility"] <= 1.0
            assert 0.0 <= r["block_rate"] <= 1.0
            assert isinstance(r["is_pareto"], int)
            # defense_names is JSON array
            names = r["defense_names"]
            parsed = names if isinstance(names, list) else json.loads(names)
            assert isinstance(parsed, list)


def test_recorder_no_op_when_disabled(tmp_path=None):
    """Recorder with record_attack before __enter__ is a no-op."""
    from storage import Recorder
    from attacks.base import AttackResult, AttackSeverity

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "noop.db")
        r = Recorder(mode="single", db_path=db_path)
        # Don't enter context; record_attack should silently no-op
        r.record_attack(AttackResult(
            attack_name="phantom", severity=AttackSeverity.LOW,
            success=False, blocked_by=[], metadata={},
        ))
        # No DB file written
        assert not Path(db_path).exists(), "DB created without context entry"


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
        else:
            passed += 1
            print(f"  ok    {name}")
    print(f"\n{passed}/{passed+failed} tests passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_all())
