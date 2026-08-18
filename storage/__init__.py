"""SQLite-backed trace storage for the Agent Red Team Platform (v0.4 B2).

Four tables: `runs`, `attack_results`, `tradeoff_points`, plus a
`calibration_reports` table for the per-run calibration report. All
writes are append-only; the dashboard reads them to show history.

The DB lives at `<project_root>/storage/agent_redteam.db` by default
and is created on first call. SQLite + WAL mode is enough for
single-process usage; multi-process dashboard + CLI use the same file
safely.
"""

from .db import (
    DEFAULT_DB_PATH,
    connect,
    init_schema,
    SCHEMA_VERSION,
)
from .recorder import (
    Recorder,
    current_recorder,
    list_runs,
    get_run_aggregates,
    list_attack_results,
    list_tradeoff_points,
    list_calibration_reports,
    count_calibration_reports_by_source,
    CALIBRATION_SOURCE_TAGS,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "connect",
    "init_schema",
    "SCHEMA_VERSION",
    "Recorder",
    "current_recorder",
    "list_runs",
    "get_run_aggregates",
    "list_attack_results",
    "list_tradeoff_points",
    "list_calibration_reports",
    "count_calibration_reports_by_source",
    "CALIBRATION_SOURCE_TAGS",
]
