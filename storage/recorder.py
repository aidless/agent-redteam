"""Recorder API (v0.4 B2).

A `Recorder` is the public entry point for writing run results to
SQLite. Use it as a context manager so the run row is always closed
(finished_at populated, status set):

    from storage import Recorder

    with Recorder(mode="single", target_provider="mock",
                  target_model="mock-model-v1", rounds=100) as rec:
        for attack_result in ...:
            rec.record_attack(attack_result)
        rec.finalize(total_cost_usd=0.0, total_input_tokens=0, total_output_tokens=0)

The `current_recorder()` helper returns the active recorder inside
the `with` block so call sites deep in the stack don't have to
thread it through. Tests can simply NOT use a Recorder and the
writes become no-ops (the recorder helpers are no-ops when no
recorder is active).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from .db import connect, init_schema


# Thread-/async-safe active recorder
_active: ContextVar = ContextVar("agent_redteam_recorder", default=None)


def current_recorder() -> Optional["Recorder"]:
    """Return the active Recorder inside a `with Recorder(...)` block,
    or None if no recorder is active."""
    return _active.get()


class Recorder:
    """Append-only writer for one run.

    Parameters
    ----------
    mode            : 'single' | 'multi' | 'tradeoff'
    target_provider : LLM provider name (e.g. 'mock', 'openai')
    target_model    : LLM model name
    rounds          : how many episodes / rounds the run executed
    config_yaml     : full config text (optional)
    notes           : free-form notes (optional)
    db_path         : override default DB location
    """

    def __init__(self, mode: str = "single",
                 target_provider: Optional[str] = None,
                 target_model: Optional[str] = None,
                 rounds: Optional[int] = None,
                 config_yaml: Optional[str] = None,
                 notes: Optional[str] = None,
                 db_path: Optional[str] = None):
        self.mode = mode
        self.target_provider = target_provider
        self.target_model = target_model
        self.rounds = rounds
        self.config_yaml = config_yaml
        self.notes = notes
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._run_id: Optional[int] = None
        self._closed = False
        self._token = None
        self._lock = threading.Lock()

    # ---- context manager ----

    def __enter__(self) -> "Recorder":
        self._conn = connect(self.db_path)
        init_schema(self._conn)
        cur = self._conn.execute(
            "INSERT INTO runs (mode, target_provider, target_model, rounds, "
            "config_yaml, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (self.mode, self.target_provider, self.target_model,
             self.rounds, self.config_yaml, self.notes),
        )
        self._run_id = int(cur.lastrowid)
        self._token = _active.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._conn is not None and self._run_id is not None:
                status = "ok" if exc_type is None else f"error:{exc_type.__name__}"
                self._conn.execute(
                    "UPDATE runs SET finished_at = datetime('now'), notes = "
                    "COALESCE(notes, '') || ? WHERE id = ?",
                    (f" [status={status}]", self._run_id),
                )
        finally:
            if self._token is not None:
                _active.reset(self._token)
            if self._conn is not None:
                self._conn.close()
            self._closed = True

    @property
    def run_id(self) -> Optional[int]:
        return self._run_id

    @property
    def closed(self) -> bool:
        return self._closed

    # ---- recorders for individual result types ----

    def record_attack(self, attack_result) -> None:
        """Append one AttackResult. Accepts any object with the v0.2+
        AttackResult dataclass interface."""
        if self._conn is None or self._run_id is None:
            return
        blocked_by = getattr(attack_result, "blocked_by", []) or []
        meta = getattr(attack_result, "metadata", {}) or {}
        sev = getattr(attack_result, "severity", None)
        sev_str = getattr(sev, "value", str(sev)) if sev is not None else None
        self._conn.execute(
            "INSERT INTO attack_results "
            "(run_id, attack_name, severity, success, blocked_by, "
            " total_cost_usd, elapsed_ms, response_preview) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self._run_id,
                getattr(attack_result, "attack_name", "?"),
                sev_str,
                1 if getattr(attack_result, "success", False) else 0,
                json.dumps(list(blocked_by)),
                float(meta.get("total_cost_usd", 0.0)),
                float(getattr(attack_result, "elapsed_ms", 0.0)),
                str(meta.get("response_preview", ""))[:500],
            ),
        )

    def record_tradeoff_point(self, point, is_pareto: bool = False) -> None:
        """Append one TradeoffPoint."""
        if self._conn is None or self._run_id is None:
            return
        self._conn.execute(
            "INSERT INTO tradeoff_points "
            "(run_id, n_defenses_on, defense_names, task_utility, "
            " block_rate, total_cost_usd, total_latency_ms, is_pareto) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self._run_id,
                int(getattr(point, "n_defenses_on", 0)),
                json.dumps(list(getattr(point, "defense_names", []))),
                float(getattr(point, "task_utility", 0.0)),
                float(getattr(point, "block_rate", 0.0)),
                float(getattr(point, "total_cost_usd", 0.0)),
                float(getattr(point, "total_latency_ms", 0.0)),
                1 if is_pareto else 0,
            ),
        )

    def record_calibration(self, source: str, report) -> None:
        """Append one CalibrationReport snapshot.

        `report` may be a CalibrationReport or any object exposing the
        same attribute names (ece/jsd/entropy/cv/gamma_temporal/gamma).
        """
        if self._conn is None or self._run_id is None:
            return
        self._conn.execute(
            "INSERT INTO calibration_reports "
            "(run_id, source, ece, jsd, entropy, cv, "
            " gamma_temporal, gamma, impossible) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self._run_id,
                str(source),
                float(getattr(report, "ece", 0.0)),
                float(getattr(report, "jsd", 0.0)),
                float(getattr(report, "entropy", 0.0)),
                float(getattr(report, "cv", 0.0)),
                float(getattr(report, "gamma_temporal", 0.0)),
                float(getattr(report, "gamma", 0.0)),
                1 if getattr(report, "impossible", False) else 0,
            ),
        )

    def finalize(self, total_cost_usd: float = 0.0,
                 total_input_tokens: int = 0,
                 total_output_tokens: int = 0) -> None:
        """Update the run row with final aggregates."""
        if self._conn is None or self._run_id is None:
            return
        self._conn.execute(
            "UPDATE runs SET total_cost_usd = ?, total_input_tokens = ?, "
            "total_output_tokens = ? WHERE id = ?",
            (float(total_cost_usd), int(total_input_tokens),
             int(total_output_tokens), self._run_id),
        )


# ---------------------------------------------------------------------------
# Read helpers (used by the dashboard)
# ---------------------------------------------------------------------------

def list_runs(db_path: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent `limit` runs, newest first.

    Each row is augmented with: ``n_attacks``, ``n_blocked``,
    ``n_tradeoff_pts``, ``n_calibration_reports`` — derived via LEFT JOIN
    aggregations so the dashboard can render a single per-run summary
    without N additional queries.
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT r.*, "
            "       COALESCE(ar.n_attacks, 0)       AS n_attacks, "
            "       COALESCE(ar.n_blocked, 0)       AS n_blocked, "
            "       COALESCE(tp.n_pts, 0)           AS n_tradeoff_pts, "
            "       COALESCE(tp.n_pareto, 0)        AS n_pareto_pts, "
            "       COALESCE(cr.n_reports, 0)       AS n_calibration_reports "
            "FROM runs r "
            "LEFT JOIN ("
            "  SELECT run_id, COUNT(*) AS n_attacks, "
            "         SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS n_blocked "
            "  FROM attack_results GROUP BY run_id"
            ") ar ON ar.run_id = r.id "
            "LEFT JOIN ("
            "  SELECT run_id, COUNT(*) AS n_pts, "
            "         SUM(CASE WHEN is_pareto = 1 THEN 1 ELSE 0 END) AS n_pareto "
            "  FROM tradeoff_points GROUP BY run_id"
            ") tp ON tp.run_id = r.id "
            "LEFT JOIN ("
            "  SELECT run_id, COUNT(*) AS n_reports "
            "  FROM calibration_reports GROUP BY run_id"
            ") cr ON cr.run_id = r.id "
            "ORDER BY r.started_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_run_aggregates(run_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Return aggregate metrics for one run, joining attack_results."""
    conn = connect(db_path)
    try:
        run = conn.execute(
            "SELECT * FROM runs WHERE id = ?", (int(run_id),)
        ).fetchone()
        if run is None:
            return {"error": f"run_id {run_id} not found"}
        run_d = dict(run)
        attacks = conn.execute(
            "SELECT COUNT(*) AS n, "
            "       SUM(success) AS n_success, "
            "       AVG(total_cost_usd) AS avg_cost "
            "FROM attack_results WHERE run_id = ?",
            (int(run_id),),
        ).fetchone()
        n_total = attacks["n"] or 0
        n_success = attacks["n_success"] or 0
        run_d["attack_count"] = n_total
        run_d["attack_success_count"] = n_success
        run_d["attack_block_count"] = n_total - n_success
        run_d["attack_block_rate"] = (
            (n_total - n_success) / n_total if n_total else 0.0
        )
        return run_d
    finally:
        conn.close()


def list_attack_results(run_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all attack_results rows for one run."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM attack_results WHERE run_id = ? ORDER BY id",
            (int(run_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_tradeoff_points(run_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all tradeoff_points rows for one run, sorted by n_defenses_on."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM tradeoff_points WHERE run_id = ? "
            "ORDER BY n_defenses_on, block_rate",
            (int(run_id),),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["defense_names"] = json.loads(d.get("defense_names") or "[]")
            except Exception:
                d["defense_names"] = []
            out.append(d)
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Calibration-history read helpers (v0.4 B6 — historical calibration tab)
# ---------------------------------------------------------------------------

# Schema-allowed source tag values. Used by the dashboard filter UI and
# by tests for sanity checking. Keep in sync with the strings emitted
# by `calibration_runner.run_calibration_recorded` and dashboard.
CALIBRATION_SOURCE_TAGS = (
    "calibration_runner",      # CLI default source
    "cli_calibration_runner",  # CLI explicit source
    "dashboard_run",           # dashboard "Run calibration" button
    "post_run_multi",          # auto-fired after multi-agent run
)


def list_calibration_reports(
    source: Optional[Union[str, List[str]]] = None,
    limit: int = 500,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return historical calibration reports joined with their `runs` row.

    Ordered by `runs.started_at` ascending so a trend chart can plot
    metrics over time directly. Each returned dict has the calibration
    metric columns plus ``started_at``, ``finished_at``, ``mode``,
    ``target_provider``, ``target_model``, ``rounds`` from the
    parent run row.

    Parameters
    ----------
    source : str | List[str] | None
        If given, filter `source` (or `source IN (...)` if a list).
        Pass None for no filter.
    limit : int
        Max rows to return. Defaults to 500 (well under 100k default
        SQLite parameter limit).
    """
    conn = connect(db_path)
    try:
        params: List[Any] = []
        where = ""
        if source is None:
            pass
        elif isinstance(source, (list, tuple, set)):
            if not source:
                return []
            placeholders = ",".join("?" for _ in source)
            where = f"WHERE cr.source IN ({placeholders})"
            params.extend(str(s) for s in source)
        else:
            where = "WHERE cr.source = ?"
            params.append(str(source))
        sql = (
            "SELECT cr.id            AS report_id, "
            "       cr.run_id, "
            "       cr.source, "
            "       cr.ece, "
            "       cr.jsd, "
            "       cr.entropy, "
            "       cr.cv, "
            "       cr.gamma_temporal, "
            "       cr.gamma, "
            "       cr.impossible, "
            "       r.started_at, "
            "       r.finished_at, "
            "       r.mode, "
            "       r.target_provider, "
            "       r.target_model, "
            "       r.rounds "
            "FROM calibration_reports cr "
            "JOIN runs r ON r.id = cr.run_id "
            f"{where} "
            "ORDER BY r.started_at ASC, cr.id ASC "
            "LIMIT ?"
        )
        params.append(int(limit))
        rows = conn.execute(sql, params).fetchall()
        out: List[Dict[str, Any]] = [dict(r) for r in rows]
        # Coerce JSON-ish bool columns to native Python bool for UI / tests.
        for d in out:
            d["impossible"] = bool(d.get("impossible"))
        return out
    finally:
        conn.close()


def count_calibration_reports_by_source(
    db_path: Optional[str] = None,
) -> Dict[str, int]:
    """Return {source: count} for all rows in `calibration_reports`.

    Cheap aggregation (single GROUP BY). Used by the dashboard filter
    UI to populate checkboxes with counts.
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT source, COUNT(*) AS n FROM calibration_reports "
            "GROUP BY source ORDER BY n DESC"
        ).fetchall()
        return {r["source"]: int(r["n"]) for r in rows}
    finally:
        conn.close()