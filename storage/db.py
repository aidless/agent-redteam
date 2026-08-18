"""SQLite connection + schema for trace persistence (v0.4 B2).

Tables:
- runs               : one row per `run_redteam.py` invocation
- attack_results     : one row per `AttackResult` produced
- tradeoff_points    : one row per `TradeoffPoint`
- calibration_reports: one row per `CalibrationReport` snapshot

All write paths go through `Recorder` (storage/recorder.py). This
file only owns the schema and the connect/init helpers.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Union

# DB lives inside the project so the dashboard can find it without
# any extra config. Tests override via the `connect(db_path=...)` arg.
DEFAULT_DB_PATH: Path = Path(__file__).resolve().parent / "agent_redteam.db"

SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Schema (idempotent — safe to call repeatedly)
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    mode            TEXT    NOT NULL,            -- 'single' | 'multi' | 'tradeoff'
    target_provider TEXT,
    target_model    TEXT,
    rounds          INTEGER,
    config_yaml     TEXT,
    notes           TEXT,
    total_cost_usd  REAL    DEFAULT 0,
    total_input_tokens  INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attack_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    attack_name   TEXT    NOT NULL,
    severity      TEXT,
    success       INTEGER NOT NULL,             -- 0 | 1
    blocked_by    TEXT,                          -- JSON array string
    total_cost_usd REAL DEFAULT 0,
    elapsed_ms    REAL DEFAULT 0,
    response_preview TEXT
);

CREATE TABLE IF NOT EXISTS tradeoff_points (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    n_defenses_on   INTEGER NOT NULL,
    defense_names   TEXT,                         -- JSON array string
    task_utility    REAL    NOT NULL,
    block_rate      REAL    NOT NULL,
    total_cost_usd  REAL    DEFAULT 0,
    total_latency_ms REAL   DEFAULT 0,
    is_pareto       INTEGER DEFAULT 0            -- 0 | 1
);

CREATE TABLE IF NOT EXISTS calibration_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    source        TEXT,                          -- e.g. 'episode_aggregated_scores'
    ece           REAL,
    jsd           REAL,
    entropy       REAL,
    cv            REAL,
    gamma_temporal REAL,
    gamma         REAL,
    impossible    INTEGER                         -- 0 | 1
);

CREATE INDEX IF NOT EXISTS idx_attack_results_run_id    ON attack_results(run_id);
CREATE INDEX IF NOT EXISTS idx_tradeoff_points_run_id   ON tradeoff_points(run_id);
CREATE INDEX IF NOT EXISTS idx_calibration_reports_run_id ON calibration_reports(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_started_at          ON runs(started_at);
"""


# ---------------------------------------------------------------------------
# Connect + init helpers
# ---------------------------------------------------------------------------

def connect(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open (and create if needed) the SQLite database.

    Sets WAL mode for safe concurrent reads (dashboard + CLI) and
    `row_factory = sqlite3.Row` so callers can use dict-style access.
    """
    p = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables (idempotent). Records schema version."""
    conn.executescript(SCHEMA)
    # Record schema version (ignore if already present)
    try:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
    except sqlite3.IntegrityError:
        pass  # version already recorded


@contextmanager
def session(db_path: Optional[Union[str, Path]] = None,
            init: bool = True) -> Iterator[sqlite3.Connection]:
    """Context manager: `with session() as conn: ...`

    Commits on success, rolls back on exception. The connection is
    always closed.
    """
    conn = connect(db_path)
    try:
        if init:
            init_schema(conn)
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()