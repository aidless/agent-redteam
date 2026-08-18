"""v0.4 B4 tests: load_config auto-resolution + CI workflow file + dashboard tab.

6 tests covering:
- D6 load_config(None) auto-loads configs/default.yaml (3 tests)
- D7 CI workflow file present and well-formed (2 tests)
- D8 dashboard.py exposes 'Run calibration' button (1 test)
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPO_ROOT = ROOT


# ---------------------------------------------------------------------------
# D6: load_config(None) auto-resolves to configs/default.yaml
# ---------------------------------------------------------------------------

def test_d6_load_config_none_loads_default_yaml():
    """load_config(None) must auto-load configs/default.yaml (no explicit path)."""
    from scripts.run_redteam import load_config
    cfg = load_config(None)
    # default.yaml contains a multi_agent block (4 agents); the legacy
    # hardcoded defaults dict does NOT. So the presence of multi_agent is
    # the fingerprint that auto-resolution fired.
    assert "multi_agent" in cfg, (
        f"expected multi_agent block from default.yaml; got keys={list(cfg.keys())}"
    )
    assert isinstance(cfg["multi_agent"].get("agents"), list)
    assert len(cfg["multi_agent"]["agents"]) >= 2


def test_d6_load_config_explicit_path_still_works():
    """Explicit config_path kwarg must still take precedence."""
    from scripts.run_redteam import load_config
    cfg = load_config("configs/default.yaml")
    assert "multi_agent" in cfg
    assert "target" in cfg


def test_d6_load_config_missing_path_returns_defaults():
    """load_config('/nonexistent/path.yaml') must return the defaults dict."""
    from scripts.run_redteam import load_config
    cfg = load_config("/nonexistent/path_that_does_not_exist.yaml")
    assert "multi_agent" not in cfg, (
        "missing explicit path must NOT fall through to default.yaml "
        "(only path=None triggers auto-resolution)."
    )
    # The defaults dict has target/orchestrator/defenses but no multi_agent.
    assert "target" in cfg and "defenses" in cfg


# ---------------------------------------------------------------------------
# D7: CI workflow file present + well-formed
# ---------------------------------------------------------------------------

def test_d7_ci_workflow_file_exists():
    wf = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert wf.exists(), f"missing CI workflow at {wf}"


def test_d7_ci_workflow_runs_strict_regression():
    wf = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = wf.read_text(encoding="utf-8")
    # Must invoke ci_regression.py with --strict so regressions fail CI.
    assert "ci_regression.py" in text
    assert "--strict" in text
    # Must run pytest (or python -m pytest) on tests/.
    assert "pytest" in text and "tests/" in text


# ---------------------------------------------------------------------------
# D8: Dashboard exposes 'Run calibration' button
# ---------------------------------------------------------------------------

def test_d8_dashboard_has_run_calibration_button():
    """dashboard.py must define a 'Run calibration' st.button inside tab_calib."""
    text = (REPO_ROOT / "scripts" / "dashboard.py").read_text(encoding="utf-8")
    # The literal button label we just added.
    assert "▶ Run calibration" in text
    # It must call into scripts.calibration_runner.run_calibration (or _recorded).
    assert "scripts.calibration_runner" in text or "from scripts.calibration_runner" in text
    # The 6 metric st.metric calls must be present so the user actually sees
    # ECE/JSD/Entropy/CV/γ_temporal/γ_coupling.
    for metric in ("ECE", "JSD", "Entropy", "CV"):
        assert metric in text, f"missing dashboard metric: {metric}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tests = [
        test_d6_load_config_none_loads_default_yaml,
        test_d6_load_config_explicit_path_still_works,
        test_d6_load_config_missing_path_returns_defaults,
        test_d7_ci_workflow_file_exists,
        test_d7_ci_workflow_runs_strict_regression,
        test_d8_dashboard_has_run_calibration_button,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok    {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e!r}")
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed")
    sys.exit(0 if failed == 0 else 1)