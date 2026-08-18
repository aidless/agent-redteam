# Agent Red Team Platform

> **Status:** v0.4 B6 — 86 tests passing, CI/CD with multi-Python matrix, GitHub Actions
> **Purpose:** Red-vs-blue security evaluation harness for multi-agent LLM systems
> **License:** Apache 2.0

![Tests](https://img.shields.io/badge/tests-86%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

---

## What is this?

A reproducible evaluation platform that stress-tests multi-agent LLM systems
against **12 categories of adversarial attacks** and measures the effectiveness
of **5 defensive layers**. The platform supports a Streamlit dashboard for
real-time red-vs-blue combat visualization.

The platform was developed to address two open problems in multi-agent LLM reliability:

1. **Compositional attacks** — attacks that chain across agent boundaries
   (e.g., prompt-injection → tool-call redirect → memory poisoning).
2. **Defense–autonomy tradeoff** — how strict must defenses be before
   agent task utility collapses?

## Project Structure

```
agent_redteam/
├── README.md                  # This file
├── PROJECT_STATUS.md          # Progress tracker (v0.4 B6)
├── .env.example               # Environment variable template (copy to .env)
├── .gitignore                 # Excludes .env, outputs/, storage/*.db
├── attacks/                   # Attack vector implementations (12 categories)
│   ├── base.py                # Attack + AttackResult + AttackSeverity
│   ├── v01_direct_injection.py .. v12_compositional.py  # [v0.3] 12 classes
│   └── loader.py              # [v0.3] load_attack_vectors()
├── aggregators/               # [v0.3] 7-aggregator pipeline (survey §7)
│   ├── base.py                # VerifierOutput + AggregatedDecision
│   └── implementations.py     # MajorityVote .. AdaptiveHybrid
├── memory/                    # [v0.3 + v0.4 B1] Memory architectures
│   ├── base.py                # MemoryStore ABC
│   ├── append_only.py         # §6 baseline
│   ├── summarization.py       # §6 with LLM-based summarization
│   ├── rag_filter.py          # §6 RAG with pluggable embedder
│   └── embeddings.py          # [v0.4 B1] Embedder ABC + 3 impls
├── metrics/                   # [v0.3] Calibration metrics (survey §2.2)
│   └── calibration.py         # ECE, JSD, H, CV, γ_temporal, γ, impossibility
├── storage/                   # [v0.4 B2] SQLite trace persistence
│   ├── db.py                  # 5-table schema (WAL mode)
│   └── recorder.py            # Recorder context manager
├── defenses/                  # Defense layer implementations (5 layers)
│   ├── base.py                # Defense base class + interface
│   ├── input_separation.py    # Layer 1: input trust separation
│   ├── tool_whitelist.py      # Layer 2: tool-call whitelist
│   ├── output_filter.py       # Layer 3: output filtering
│   ├── behavior_audit.py      # Layer 4: behavioral auditing
│   └── constitutional.py      # Layer 5: constitutional AI checks
├── targets/                   # [v0.2] LLM target abstractions
│   ├── base.py                # LLMTarget ABC + TargetResponse dataclass
│   ├── mock_target.py         # Mock target (free, deterministic)
│   ├── openai_target.py       # OpenAI API (gpt-4o, gpt-3.5-turbo, o1-*)
│   ├── anthropic_target.py    # Anthropic API (claude-3-5-sonnet, claude-3-opus)
│   └── local_target.py        # Local llama.cpp (OpenAI-compatible HTTP @ :8080)
├── orchestrator/              # Coordinates target + defenses + attacks
│   ├── single_agent.py        # [v0.2] SingleAgentOrchestrator
│   └── multi_agent.py         # [v0.3] MultiAgentOrchestrator (BOUNDARY_SYNC + verifier capture)
├── data/                      # Attack datasets (JSON)
│   └── attack_vectors.json    # 50 attack samples (12 categories)
├── configs/
│   └── default.yaml           # Provider/model/defense/cost/multi-agent/memory/aggregator config
├── scripts/                   # Executable entry points
│   ├── run_redteam.py         # Main runner (--mode {single,multi}, --record default on)
│   ├── tradeoff.py            # [v0.3] Defense-autonomy sweep + run_tradeoff_recorded()
│   └── dashboard.py           # Streamlit dashboard (4 tabs: Sim / Tradeoff / Calibration / History)
├── tests/                     # 46 tests across 4 files
│   ├── test_targets.py        # 9 — v0.2 LLM target smoke tests
│   ├── test_v03.py            # 17 — v0.3 6-task additions
│   ├── test_v04.py            # 9 — v0.4 B1 pluggable embedders
│   └── test_v04_storage.py    # 11 — v0.4 B2 SQLite storage
├── storage/                   # [v0.4 B2] Runtime DB lives here
│   └── agent_redteam.db       # (gitignored) Created on first Recorder.__enter__
├── outputs/                   # Generated logs, traces, scores
└── docs/
    └── USAGE.md               # How to run + interpret results
```

## Quickstart

```bash
# Install (Python 3.11+)
cd agent-redteam
uv venv .venv
uv pip install -r requirements.txt

# Optional: copy .env.example to .env and fill in API keys
cp .env.example .env

# Run smoke tests (no API keys required)
python tests/test_targets.py

# Run the red-vs-blue simulation (default: mock target)
python scripts/run_redteam.py --target mock --rounds 100

# Run with real LLM (needs API key)
python scripts/run_redteam.py --target openai --model gpt-4o-mini --rounds 20 --max-cost-usd 5.00
python scripts/run_redteam.py --target anthropic --rounds 20

# Launch the Streamlit dashboard
python -m streamlit run scripts/dashboard.py

# CI regression gate (strict — exit 1 if any suite < baseline)
python scripts/ci_regression.py --strict

# Multi-Python matrix (3.10 / 3.11 / 3.12)
python scripts/ci_multi_python.py --quick
```

## Relationship to Survey

| Survey Section | Platform Component |
|---|---|
| §8.2 Attack Taxonomy (12 vectors) | `attacks/` (12 categories, 50 samples in JSON) |
| §8.3 Defense Layers (5 layers) | `defenses/` (5 modules) |
| §8.4 Calibration as a Security Property | v0.2: tracked in `target_response.tokens` |
| §8.5 Compliance Context (EU AI Act) | v0.3: `configs/compliance_profiles.yaml` |
| §8.6 Compositional Attacks | `data/attack_vectors.json::V12_compositional` |
| §8.7 Defense–Autonomy Tradeoff | v0.2: cost / latency tracked per defense |

## License

Apache 2.0 — open-source companion to the TMLR survey.

## Authors

Anonymous Authors (TMLR double-blind compliant). Full author list to be
added in the camera-ready version.

## Changelog

- **v0.4 B6 (2026-07-24)**: Coverage sprint + Historical Calibration tab +
  CI multi-Python matrix + version control init. 4 polish tasks delivered
  (A: coverage; B: git; C: dashboard trend; D: multi-Python matrix):
  - **B6-A coverage sprint** (25 tests in `tests/test_v04_b6.py`):
    - **A1 factories** (6 tests): `create_target(mock/raises/overrides)` +
      `create_defenses(default/disable/none)` — covers both happy and edge
      paths in `targets/factory.py` and `defenses/factory.py`.
    - **A2 aggregators** (9 tests): every one of the 7 `aggregators/`
      classes gets a smoke test that constructs a small `VerifierOutput`
      stream and checks the `AggregatedDecision` invariants (label is
      0/1, score in [0,1], method name, per_verifier length). Plus
      `make_aggregator()` factory round-trip for all 7 class names.
    - **A3 attacks** (5 tests): all 12 attack classes round-trip through
      `load_attack_vectors()`; V01/V03/V06/V10 each tested for the
      "no orchestrator in `system_state`" error path that any user-
      facing caller hits first.
    - **A4 Recorder** (3 tests): `finalize()` writes `finished_at`
      only when `record_attack` was called at least once; `finalize()`
      without any record call is a no-op (no spurious empty row);
      `current_recorder()` defaults to `None` outside a `with`
      context.
    - **A5 MultiAgentOrchestrator** (2 tests): `T_rounds=0` returns an
      empty `EpisodeResult` (degenerate input); single-agent config
      with no `verifier` agent produces no `AggregatedDecision` (so
      `aggregated` is `None`, not a fake zero).
  - **B6-B git version control init**: project was 0-tracked under
    `F:/Research` parent repo. Now committed as standalone repo: **69 files** (68 source
    + `.gitattributes`). `.gitattributes` enforces `eol=lf` for all
    tracked text files (Python / YAML / TOML / .tex / .bib / etc.) and
    `eol=crlf` for Windows-only `.cmd` shims. `core.autocrlf=false`
    set locally so future `git add` doesn't re-introduce CRLF.
    Eliminates the cross-platform diff noise that bit us earlier.
  - **B6-C Dashboard Historical Calibration tab** (5th tab):
    - **C1** New `storage.list_calibration_reports(source, limit)` and
      `storage.count_calibration_reports_by_source()` read helpers
      (join `calibration_reports` with `runs` for `started_at` /
      `target_*` / `mode` context).
    - **C2** 6-metric trend chart (`st.line_chart` over ECE / JSD /
      entropy / CV / γ_temporal / γ) with a multi-select for which
      metrics to plot.
    - **C3** Source filter: checkboxes for each known source tag
      (`calibration_runner`, `cli_calibration_runner`,
      `dashboard_run`, `post_run_multi`) + any source that actually
      has rows in the DB; counts come from a single GROUP BY query.
    - **C4** "Impossible-triangle" fraction panel + raw-row dataframe
      + JSON dump (capped at 50 for perf).
    - 6 new tests in `tests/test_v04_b6_calib_history.py` covering
      list/filter/limit/groups/source_tags/dashboard-wiring.
  - **B6-D CI multi-Python matrix** (3.10 / 3.11 / 3.12):
    - **D1** `scripts/ci_multi_python.py` — for each Python in the
      matrix, create a throw-away venv, pip-install `requirements.txt`
      + pytest, then run the same direct-runner suite pipeline as
      `ci_regression.py`. Outputs a Markdown matrix table; supports
      `--py 3.12` (restrict), `--quick` (B3/B4/B6 suites only),
      `--json` (machine-readable).
    - **D2** `.github/workflows/ci_multi_python.yml` — companion to
      `ci.yml`. Triggers only on `workflow_dispatch` (manual) +
      weekly Monday 06:00 UTC cron. Runs each suite per Python with
      `fail-fast: false` so every cell of the matrix is informational.
    - **D3 compat fix**: `requirements.txt` previously pinned
      `pandas==3.0.5` and `numpy==2.4.6`, which **do not exist on
      PyPI** (pandas 3.x is unreleased; numpy 2.4.x is unreleased).
      Replaced with realistic ranges `pandas>=2.2,<3` and
      `numpy>=2.0,<3`. After fix, all 3 Pythons green.
    - **Local matrix result** (after D3):
      `3.10: 9+6+25+6=46 PASS | 3.11: 46 PASS | 3.12: 46 PASS`.
  - **Final state**:
    - `pytest tests/` → **86 passed, 1 skipped in 28.31s** (exit 0)
    - `python scripts/ci_regression.py --strict` → **93/93 passed
      across 7 suites** (exit 0)
    - `python scripts/ci_multi_python.py --quick` → 3 Python × 4
      suites × all-PASS (3.10 / 3.11 / 3.12)
    - git: `git log --oneline | head` shows the new `feat(agent_redteam):
      v0.4 B5 + version control init` commit (69 files).
- **v0.4 B5 (2026-07-24)**: Polish + requirements.txt + 4 latent-bug fixes +
  `test_v04.py` recovery.
  - **P1 CI workflow indent** unified to 2-space throughout.
  - **P2 Dashboard import**: deliberately kept inside the button handler
    (consistent with all other tabs — `tab_tradeoff`, `tab_history`,
    `tab_calib` metrics all use lazy imports to avoid heavy deps on
    reruns when the user is on a different tab).
  - **P3 local pytest**: `pytest==9.0.2` installed into the project venv
    via `uv pip install`. Local `python -m pytest tests/ --collect-only
    -q` collects all 61 tests in 0.25s.
  - **P4 `requirements.txt`**: 7 runtime + 1 dev dep pinned (`openai`,
    `anthropic`, `streamlit`, `pandas`, `numpy`, `python-dotenv`,
    `PyYAML`, `pytest`). CI workflow now `pip install -r requirements.txt`
    instead of duplicating the list inline. Drift risk between local venv
    and CI is gone.
  - **Latent fix #1 (skip→failure)**: `tests/test_v04.py` and
    `tests/test_v04_b3.py` runners now catch `BaseException` (not just
    `Exception`) and use `_pytest.skip()` so pytest and direct runner
    agree on skip semantics. 1 formerly-failing skip now correctly
    classified.
  - **Latent fix #2 (recursion guard)**: `ci_regression.evaluate()`
    reads `_CI_REGRESSION_INVOKED_BY_SUITE` env var (set by
    `run_suite`) and short-circuits when a suite calls itself
    recursively via subprocess. Prevents `test_v04_b3.py::test_d4_*`
    from infinite-looping under pytest.
  - **Latent fix #3 (clean-baseline logic)**: `test_d4_evaluate_clean`
    rewritten to monkey-patch `run_suite` (synthetic returns = baseline)
    rather than setting baseline=0 (which always regressed).
  - **Latent fix #4 (recurse-skip)**: `test_d4_evaluate_regression_detection`
    now skips itself via `_pytest.skip()` when the recursion guard is
    active (cannot meaningfully exercise `evaluate()` from inside the
    loop that triggered it).
  - **Recovery**: `tests/test_v04.py` (9 tests + runner) was deleted by
    an external process between sessions. Reconstructed from git history
    + my earlier Edit content; aligned with current
    `memory/embeddings.py` API.
  - **Final state**:
    - `pytest tests/` → **61 passed, 1 skipped in 27.47s** (exit 0)
    - `python scripts/ci_regression.py --strict` → **62/62 passed
      across 6 suites** (exit 0)
    - All 6 direct runners (`python tests/test_*.py`) → pass.
- **v0.4 B4 (2026-07-23)**: `load_config(None)` auto-resolves + CI workflow file + Dashboard calibration button. 4 tasks delivered:
  - **D6 `load_config` auto-resolution**: when `path` is `None`, now auto-loads `<repo>/configs/default.yaml` (pre-existing B3 hack removed). Falls back to hardcoded `defaults` only if that file is missing. Eliminates the need to pass `config_path="configs/default.yaml"` explicitly from Python API callers. Test: `test_d6_load_config_none_loads_default_yaml`.
  - **D7 GitHub Actions CI workflow**: new `.github/workflows/ci.yml` runs `pytest tests/ -q` then `python scripts/ci_regression.py --strict --json`. Triggers on push to `main` and on PRs. Strict mode so regressions fail the build.
  - **D8 Dashboard "Run calibration" tab**: `tab_calib` now has a 4-column interactive panel (`seed`, `n`, `bias`, `Persist to SQLite` checkbox) + "▶ Run calibration" button. Calls `scripts.calibration_runner.run_calibration_recorded()` (when checkbox on) or `run_calibration()` (when off) and renders the 6 metrics as `st.metric` cards + the notes dict in an expander.
  - **D9 6 new tests in `tests/test_v04_b4.py`** (D6 × 3: auto-resolve + explicit path + missing path; D7 × 2: workflow file exists + runs `--strict`; D8 × 1: dashboard button present + 6 metrics wired). Total now **61/61** (no regression). CI gate `BASELINE` dict bumped to include `test_v04_b3.py:9` + `test_v04_b4.py:6` so future regressions of new tests are caught.
- **v0.4 B3 (2026-07-23)**: CI regression gate + post-run calibration + `--no-record` flag.
  5 tasks delivered:
  - **D1 `--no-record` flag**: argparse tri-state group (`--record`/`--no-record`/default=true)
    on `scripts/run_redteam.py`. Use `--no-record` to skip SQLite persistence
    (e.g. for smoke / exploratory runs).
  - **D2 `calibration_runner`**: new `scripts/calibration_runner.py` with
    `synth_score_stream(n, seed, bias)` (deterministic synthetic biased-vs-clean
    score pairs), `run_calibration()` returning a full `CalibrationReport`
    (6 metrics), and `run_calibration_recorded()` wrapper that writes a
    `calibration_reports` row. CLI: `--seed/--n/--bias/--record`.
  - **D3 auto `record_calibration` after multi-mode**: `scripts/run_redteam.py`
    collects per-episode aggregated verifier scores during the multi-agent
    loop and, when ≥ 2 episodes produce aggregated decisions, fires the
    post-loop calibration block (`record_calibration("post_run_multi", report)`).
    Result appears in `results["calibration_report_recorded"] = True` and is
    visible in the Historical Runs tab.
  - **D4 CI regression gate**: new `scripts/ci_regression.py` with baseline
    counts (`test_targets.py:9, test_v03.py:17, test_v04.py:9, test_v04_storage.py:11`)
    and `--strict` / `--soft` (default) / `--update-baseline` / `--json` modes.
    `--soft` mode emits WARNs on regressions but exits 0; `--strict` exits 1
    on any regression. CI workflow: `pytest` first, then
    `python scripts/ci_regression.py` (soft) → ✅.
  - **D5 tests + docs**: 9 new tests in `tests/test_v04_b3.py`
    (D1 flag resolution × 3, D2 calibration runner × 3, D3 post-run
    calibration wiring, D4 evaluate × 2). Total now **55/55**
    (9 + 17 + 9 + 11 + 9, no regression).
- **v0.4 B2 (2026-07-23)**: SQLite trace persistence + Historical Runs tab.
  New `storage/` package with 5-table WAL-mode SQLite schema
  (`runs`, `attack_results`, `tradeoff_points`, `calibration_reports`,
  `schema_version`), a `Recorder` context manager (`enter` creates the
  run row, `exit` stamps `finished_at`), and read helpers
  (`list_runs`, `get_run_aggregates`, `list_attack_results`,
  `list_tradeoff_points`). `scripts/run_redteam.py` now records one
  `attack_results` row per round/episode for both `--mode single` and
  `--mode multi`. `scripts/tradeoff.py` gains `run_tradeoff_recorded()`
  which writes one `tradeoff_points` row per subset with the Pareto
  flag. Dashboard gets a 4th tab **🗄️ Historical Runs** with a
  run-selector, per-run aggregates, and drill-down into per-attack
  rows or per-tradeoff points. 11 new tests in `tests/test_v04_storage.py`
  (all 11 pass). Total now **46/46** (9 + 17 + 9 + 11, no regression).
  New API: `from storage import Recorder, list_runs, get_run_aggregates,
  list_attack_results, list_tradeoff_points, DEFAULT_DB_PATH`.
- **v0.4 B1 (2026-07-22)**: Pluggable embedders for RAG memory. New
  `memory/embeddings.py` with `Embedder` ABC, `TokenOverlapEmbedder`
  (v0.3 baseline, preserved), `CharNgramEmbedder` (pure-Python
  char n-gram + IDF, captures sub-word morphology), and
  `SentenceTransformerEmbedder` (real embeddings, optional).
  `default_embedder()` factory auto-falls back to char_ngram when
  `sentence-transformers` is not installed. `RAGMemory.__init__`
  gains an `embedder=` kwarg; default still uses token overlap so
  v0.3 call sites are unchanged. 9 new tests in
  `tests/test_v04.py` (all 9 pass; 1 skip if ST not installed).
  v0.2 9/9 + v0.3 17/17 still pass (no regression).
- **v0.3 (2026-07-22)**: Multi-agent + calibration + memory + aggregators + tradeoff.
  Added `metrics/calibration.py` (6 metrics from survey §2.2), `memory/` (3
  architectures from §6: append-only / summarization / RAG), `aggregators/`
  (7 implementations from §7.2), `attacks/v01..v12_*.py` (12 vector classes
  + `loader.py`), `orchestrator/multi_agent.py` (BOUNDARY_SYNC protocol,
  verifier capture, 7-aggregator pipeline), `scripts/tradeoff.py`
  (defense-autonomy sweep with GSM8K-style proxy), new tab in
  `scripts/dashboard.py`. `run_redteam.py` gains `--mode single|multi`,
  `--memory`, `--aggregator` flags. `tests/test_v03.py` adds 17 smoke
  tests (17/17 passing). v0.2 9/9 still passing (no regression).
- **v0.2 (2026-07-22)**: LLM target abstraction. Added `targets/` (4 providers),
  `orchestrator/` (single-agent), `configs/default.yaml`, `.env.example`,
  `.gitignore`, `tests/test_targets.py` (9 smoke tests). Updated `run_redteam.py`
  + `dashboard.py` with `--target` parameter and cost panel.
- **v0.1 (2026-07-22)**: Initial scaffold. 5 defense layers, 12 attack vectors
  in JSON, mock run_redteam.py, Streamlit dashboard.