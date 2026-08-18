#!/usr/bin/env python3
"""Streamlit dashboard for red-vs-blue multi-agent LLM security evaluation.

Run with:
    streamlit run scripts/dashboard.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# Add parent to path so we can import run_redteam
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from scripts.run_redteam import run_redteam


# ---------- Page config ----------

st.set_page_config(
    page_title="Agent Red Team Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------- Sidebar ----------

st.sidebar.title("🎯 Agent Red Team")
st.sidebar.markdown("""
Multi-agent LLM security evaluation harness.

**5 defense layers** vs **12 attack categories**.
Real-time red-vs-blue simulation.
""")

st.sidebar.markdown("---")
st.sidebar.markdown("### Configuration")

# Provider selector
provider = st.sidebar.selectbox(
    "LLM Provider",
    options=["mock", "openai", "anthropic", "local"],
    index=0,
    help="mock: free no-op | openai: needs OPENAI_API_KEY | anthropic: needs ANTHROPIC_API_KEY | local: needs llama.cpp server on :8080",
)

# Model selector (depends on provider)
MODEL_OPTIONS = {
    "mock":      ["mock-model-v1"],
    "openai":    ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini", "o1-preview"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
                  "claude-3-opus-20240229", "claude-3-haiku-20240307"],
    "local":     ["local-model"],
}
model_options = MODEL_OPTIONS.get(provider, ["custom-model"])
model = st.sidebar.selectbox(
    "Model",
    options=model_options,
    index=0,
)

# Cost cap (only meaningful for non-mock)
max_cost_usd = 10.0
if provider != "mock":
    max_cost_usd = st.sidebar.number_input(
        "Max cost (USD)",
        min_value=0.01, max_value=100.0, value=10.0, step=0.5,
        help="Hard cap on total spend per simulation run",
    )

rounds = st.sidebar.slider("Rounds", min_value=10, max_value=1000, value=100, step=10)
seed = st.sidebar.number_input("Random seed", min_value=0, max_value=9999, value=42)
run_button = st.sidebar.button("▶ Run simulation", type="primary")

st.sidebar.markdown("---")
st.sidebar.markdown("### Attack Categories")
ATTACK_INFO = {
    "V01_direct_prompt_injection": ("Direct Prompt Injection", "high", "🎯"),
    "V02_indirect_prompt_injection": ("Indirect Prompt Injection", "high", "🕸️"),
    "V03_jailbreak_templates": ("Jailbreak Templates (DAN/AIM)", "medium", "🔓"),
    "V04_role_hijack": ("Role Hijacking", "medium", "🎭"),
    "V05_tool_call_redirection": ("Tool-Call Redirection", "high", "🔧"),
    "V06_memory_poisoning": ("Memory Poisoning", "high", "💾"),
    "V07_output_exfiltration": ("Output Exfiltration", "high", "📤"),
    "V08_aggregator_capture": ("Verifier/Aggregator Capture", "critical", "⚖️"),
    "V09_sybil_agent": ("Sybil Agent Insertion", "critical", "👥"),
    "V10_prompt_leakage": ("System Prompt Leakage", "medium", "🔍"),
    "V11_resource_exhaustion": ("Resource Exhaustion (DoS)", "medium", "⏱️"),
    "V12_compositional": ("Compositional Multi-Vector", "critical", "🧬"),
}
for vid, (name, sev, emoji) in ATTACK_INFO.items():
    st.sidebar.markdown(f"{emoji} **{name}** ({sev})")

st.sidebar.markdown("---")
st.sidebar.markdown("### Defense Layers")
DEFENSE_INFO = [
    ("input_separation", "Input Trust Separation", "1"),
    ("tool_whitelist", "Tool-Call Whitelist", "2"),
    ("output_filter", "Output Filtering", "3"),
    ("behavior_audit", "Behavioral Auditing", "4"),
    ("constitutional", "Constitutional AI", "5"),
]
for d_id, name, layer in DEFENSE_INFO:
    st.sidebar.markdown(f"🛡️ L{layer}: **{name}**")


# ---------- Main page ----------

st.title("🎯 Red-vs-Blue: Multi-Agent LLM Security Dashboard")

col1, col2, col3 = st.columns(3)
col1.metric("Defense Layers", "5", help="input_separation, tool_whitelist, output_filter, behavior_audit, constitutional")
col2.metric("Attack Categories", "12", help="See sidebar for full list")
col3.metric("Total Attack Samples", "50", help="From data/attack_vectors.json")

# ---------- Tabs (v0.3: simulation + tradeoff + calibration) ----------

tab_sim, tab_tradeoff, tab_calib, tab_calib_history, tab_history = st.tabs([
    "🟢 Simulation",
    "⚖️ Defense × Autonomy Tradeoff",
    "📊 Calibration Metrics",
    "📈 Calibration History",
    "🗄️ Historical Runs",
])

with tab_sim:
    st.markdown("Use the sidebar to configure the simulation, then click **▶ Run simulation**.")
    # Run simulation
    run_button_local = run_button
    st.markdown("---")

with tab_tradeoff:
    st.subheader("Defense × Task-Utility × Attack-Block Tradeoff (v0.3)")
    st.markdown("""
    For each combination of 5 defense layers we measure:
    - **X** = number of defenses enabled (0..5)
    - **Y** = task utility on a 10-problem GSM8K-style proxy
    - **Z** = attack block rate across 12 vectors
    The Pareto front (blue triangles) is computed w.r.t. (max block, max utility).
    """)
    from scripts.tradeoff import run_tradeoff, pareto_front, GSM8K_PROXY, run_tradeoff_recorded
    from targets import MockLLMTarget
    from defenses.input_separation import InputSeparationDefense
    from defenses.tool_whitelist import ToolWhitelistDefense
    from defenses.output_filter import OutputFilterDefense
    from defenses.behavior_audit import BehaviorAuditDefense
    from defenses.constitutional import ConstitutionalDefense

    max_combos = st.slider("Max combinations to evaluate (cap for speed)", 2, 32, 8, 1)
    if st.button("▶ Run tradeoff sweep"):
        target = MockLLMTarget()
        base = [
            InputSeparationDefense(),
            ToolWhitelistDefense(),
            OutputFilterDefense(),
            BehaviorAuditDefense(),
            ConstitutionalDefense(),
        ]
        # v0.4 B2: wrap run with a Recorder so each (point, is_pareto) pair
        # is persisted to SQLite for later inspection in the Historical tab.
        rec_ctx = None
        n_recorded = 0
        try:
            from storage import Recorder
            rec_ctx = Recorder(
                mode="tradeoff",
                target_provider="mock",
                target_model="mock-model-v1",
                rounds=max_combos,
                config_yaml=None,
            )
            rec_ctx.__enter__()
        except Exception as e:
            print(f"[warn] tradeoff recorder init failed: {e!r}")
            rec_ctx = None
        try:
            with st.spinner(f"Evaluating {max_combos} defense subsets..."):
                if rec_ctx is not None:
                    out = run_tradeoff_recorded(
                        target, base, max_combinations=max_combos, recorder=rec_ctx,
                    )
                    pts = out["points"]
                    n_recorded = out["n_recorded"]
                else:
                    pts = run_tradeoff(target, base, max_combinations=max_combos)
        finally:
            if rec_ctx is not None:
                try:
                    rec_ctx.finalize(
                        total_cost_usd=target.total_cost_usd,
                        total_input_tokens=target.total_input_tokens,
                        total_output_tokens=target.total_output_tokens,
                    )
                    rec_ctx.__exit__(None, None, None)
                except Exception as e:
                    print(f"[warn] tradeoff recorder finalize failed: {e!r}")
        st.session_state["tradeoff_pts"] = pts
        st.session_state["tradeoff_front"] = pareto_front(pts)
        if n_recorded > 0:
            st.success(f"Done — {len(pts)} points evaluated, "
                       f"{len(st.session_state['tradeoff_front'])} on Pareto front, "
                       f"{n_recorded} persisted to SQLite.")
        else:
            st.success(f"Done — {len(pts)} points evaluated, "
                       f"{len(st.session_state['tradeoff_front'])} on Pareto front.")

    if "tradeoff_pts" in st.session_state:
        pts = st.session_state["tradeoff_pts"]
        front = st.session_state["tradeoff_front"]
        rows = [{"n_defenses": p.n_defenses_on,
                 "utility": round(p.task_utility, 3),
                 "block_rate": round(p.block_rate, 3),
                 "defenses": ", ".join(p.defense_names) or "(none)",
                 "pareto": p in front} for p in pts]
        st.dataframe(rows, use_container_width=True)
        try:
            import pandas as pd
            df = pd.DataFrame([
                {"x": p.n_defenses_on, "y": p.task_utility,
                 "z": p.block_rate, "is_front": p in front} for p in pts
            ])
            st.scatter_chart(df, x="x", y="y", size="z", color="is_front")
        except Exception as e:
            st.warning(f"Chart unavailable: {e}")

with tab_calib:
    st.subheader("Calibration metrics (v0.3)")
    st.markdown("""
    Six metrics from survey §2.2, all pure-Python (no numpy):
    ECE, JSD, H, CV, γ_temporal, γ (coupling), and the impossibility
    triangle (γ·H·CV ≥ c_min).
    """)
    from metrics import ece, jsd, entropy, cv, gamma_temporal, coupling, impossibility_triangle
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**ECE demo (15 bins)**")
        st.code(f"ece([0.0,1.0],[0,1],15) = {ece([0.0,1.0],[0,1],15):.4f}", language="text")
        st.code(f"ece([0.9,0.9],[0,0],15) = {ece([0.9,0.9],[0,0],15):.4f}  (over-confident wrong)", language="text")
        st.markdown("**JSD demo**")
        st.code(f"jsd([1,0],[0,1]) = {jsd([1,0],[0,1]):.4f}  (orthogonal)", language="text")
    with c2:
        st.markdown("**Impossibility triangle**")
        r = impossibility_triangle(2.0, 0.5, 2.0, c_min=1e-3)
        st.code(f"impossibility_triangle(2.0, 0.5, 2.0) -> product={r.product:.4f}, violated={r.violated}", language="text")
        st.markdown("**γ coupling**")
        st.code(f"coupling([0,1],[1,0]) = {coupling([0,1],[1,0]):.4f}  (=√2 = full flip)", language="text")

    st.divider()
    st.markdown("### ▶ Run a calibration sweep (v0.4 B3)")
    st.caption("Generates a synthetic biased-vs-clean score stream, computes "
               "all 6 metrics, and (optionally) persists to `calibration_reports`.")
    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        cal_seed = st.number_input("seed", min_value=0, max_value=10_000, value=42, step=1, key="cal_seed")
    with cc2:
        cal_n = st.number_input("n samples", min_value=10, max_value=2000, value=200, step=10, key="cal_n")
    with cc3:
        cal_bias = st.slider("bias", min_value=0.0, max_value=1.0, value=0.25, step=0.05, key="cal_bias")
    with cc4:
        cal_record = st.checkbox("Persist to SQLite", value=False, key="cal_record")

    if st.button("▶ Run calibration", key="cal_run"):
        try:
            from scripts.calibration_runner import run_calibration, run_calibration_recorded
            if cal_record:
                rep = run_calibration_recorded(
                    seed=int(cal_seed), n=int(cal_n), bias=float(cal_bias),
                    source_tag="dashboard_run",
                )
            else:
                rep = run_calibration(seed=int(cal_seed), n=int(cal_n), bias=float(cal_bias))
            st.success(f"Calibration done (record={cal_record}).")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("ECE", f"{rep.ece:.4f}")
                st.metric("JSD", f"{rep.jsd:.4f}")
            with c2:
                st.metric("Entropy", f"{rep.entropy:.4f}")
                st.metric("CV", f"{rep.cv:.4f}")
            with c3:
                st.metric("γ_temporal", f"{rep.gamma_temporal:.4f}")
                st.metric("γ coupling", f"{rep.gamma_coupling:.4f}")
            with st.expander("Report notes"):
                st.json(rep.notes)
        except Exception as e:
            st.error(f"Calibration failed: {e!r}")


with tab_calib_history:
    st.subheader("Historical calibration reports (v0.4 B6)")
    st.markdown("""
    Trend view over every `calibration_reports` row persisted by the
    CLI runner (`calibration_runner.py`), the dashboard **▶ Run
    calibration** button, and the auto-fired post-run hook. Six
    metrics over time — pick which sources to include.
    """)
    try:
        from storage import (
            list_calibration_reports,
            count_calibration_reports_by_source,
            CALIBRATION_SOURCE_TAGS,
        )

        # ---------- Source filter ----------
        counts = count_calibration_reports_by_source()
        all_sources_seen = sorted(counts.keys())
        # Union of known canonical tags + anything that actually exists in DB.
        options = sorted(set(CALIBRATION_SOURCE_TAGS) | set(all_sources_seen))
        st.markdown("**Source filter** (counts come from the DB):")
        fc1, fc2, fc3, fc4 = st.columns(4)
        chosen: list = []
        for i, src in enumerate(options):
            col = (fc1, fc2, fc3, fc4)[i % 4]
            n = counts.get(src, 0)
            label = f"{src} ({n})" if n else src
            default_on = n > 0
            if col.checkbox(label, value=default_on, key=f"calib_src_{src}"):
                chosen.append(src)

        # No data → helpful message + early exit
        if not chosen:
            st.info("No sources selected, or no calibration reports persisted yet. "
                    "Run a calibration from the **📊 Calibration Metrics** tab, or "
                    "from CLI: `python scripts/calibration_runner.py`.")
        else:
            rows = list_calibration_reports(source=chosen, limit=500)
            if not rows:
                st.warning("Selected sources have no rows.")
            else:
                st.markdown(
                    f"**{len(rows)} reports** (most-recent 500, "
                    f"ordered by run start time). "
                    f"Impossible fraction: "
                    f"{sum(1 for r in rows if r['impossible'])}/{len(rows)} "
                    f"= {sum(1 for r in rows if r['impossible'])/len(rows):.1%}"
                )

                # ---------- 6-metric trend chart ----------
                import pandas as pd
                df = pd.DataFrame([{
                    "started_at":      r["started_at"],
                    "ece":             r["ece"],
                    "jsd":             r["jsd"],
                    "entropy":         r["entropy"],
                    "cv":              r["cv"],
                    "gamma_temporal":  r["gamma_temporal"],
                    "gamma":           r["gamma"],
                    "source":          r["source"],
                    "impossible":      r["impossible"],
                } for r in rows])
                df["started_at"] = pd.to_datetime(df["started_at"], errors="coerce")
                df = df.dropna(subset=["started_at"]).set_index("started_at")

                st.markdown("### 📈 Trend over time")
                metric_choice = st.multiselect(
                    "Metrics to plot",
                    options=["ece", "jsd", "entropy", "cv",
                             "gamma_temporal", "gamma"],
                    default=["ece", "jsd", "gamma_temporal", "gamma"],
                    key="calib_history_metrics",
                )
                if metric_choice:
                    st.line_chart(df[metric_choice])
                else:
                    st.info("Pick at least one metric.")

                st.markdown("### 🔥 Impossible-triangle count per source")
                imp_by_src = (
                    df.groupby("source")["impossible"]
                      .sum()
                      .astype(int)
                      .reset_index()
                      .rename(columns={"impossible": "n_impossible"})
                )
                st.dataframe(imp_by_src, use_container_width=True)

                st.markdown("### 🗂 Raw rows")
                st.dataframe(
                    df.reset_index()[[
                        "started_at", "source",
                        "ece", "jsd", "entropy", "cv",
                        "gamma_temporal", "gamma", "impossible",
                    ]],
                    use_container_width=True,
                )

                # JSON dump for copy-paste / regression scripts
                with st.expander("📋 View raw JSON"):
                    st.json(rows[:50])  # cap for perf
    except Exception as e:
        st.error(f"Calibration history unavailable: {e!r}")


with tab_history:
    st.subheader("Historical runs (v0.4 B2 — SQLite)")
    st.markdown("""
    Every red-team run (`run_redteam.py` / `dashboard.py` simulation) and
    every Pareto tradeoff sweep writes one row to the platform SQLite DB
    (`storage/agent_redteam.db`). Pick a run to inspect its aggregates,
    per-attack outcomes, and (for tradeoff runs) per-point Pareto marks.
    """)
    try:
        from storage import (
            Recorder, list_runs, get_run_aggregates,
            list_attack_results, list_tradeoff_points,
            DEFAULT_DB_PATH,
        )
        st.markdown(f"**DB path:** `{DEFAULT_DB_PATH}`")

        runs = list_runs(limit=50)
        if not runs:
            st.info("No runs yet. Run a simulation or a tradeoff sweep first.")
        else:
            st.markdown(f"**{len(runs)} most recent runs:**")
            rows = [{
                "run_id": r["id"],
                "mode": r["mode"],
                "target": f"{r['target_provider']}/{r['target_model']}",
                "rounds": r["rounds"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "cost_usd": round(r.get("total_cost_usd", 0.0), 4),
                "n_attacks": r.get("n_attacks", 0),
                "n_blocked": r.get("n_blocked", 0),
                "n_tradeoff_pts": r.get("n_tradeoff_pts", 0),
            } for r in runs]
            st.dataframe(rows, use_container_width=True)

            # Per-run drill-down
            run_ids = [r["id"] for r in runs]
            chosen = st.selectbox("Drill into run_id", run_ids)
            if chosen is not None:
                agg = get_run_aggregates(chosen)
                st.markdown("**Aggregates:**")
                st.json(agg)

                if agg.get("mode") == "tradeoff":
                    pts = list_tradeoff_points(chosen)
                    if pts:
                        st.markdown(f"**{len(pts)} tradeoff points:**")
                        rows = [{
                            "n_defenses_on": p["n_defenses_on"],
                            "task_utility": round(p["task_utility"], 3),
                            "block_rate": round(p["block_rate"], 3),
                            "cost_usd": round(p["total_cost_usd"], 4),
                            "latency_ms": round(p["total_latency_ms"], 1),
                            "is_pareto": bool(p["is_pareto"]),
                            "defenses": ", ".join(p["defense_names"]),
                        } for p in pts]
                        st.dataframe(rows, use_container_width=True)
                else:
                    ars = list_attack_results(chosen)
                    if ars:
                        st.markdown(f"**{len(ars)} attack results:**")
                        rows = [{
                            "attack_name": a["attack_name"],
                            "severity": a["severity"],
                            "success": bool(a["success"]),
                            "blocked_by": ", ".join(a["blocked_by"]) if a["blocked_by"] else "(none)",
                            "elapsed_ms": round(a["elapsed_ms"], 2),
                            "cost_usd": round(a["total_cost_usd"], 4),
                        } for a in ars]
                        st.dataframe(rows, use_container_width=True)
    except Exception as e:
        st.error(f"DB unavailable: {e!r}")

# Run simulation (kept outside tabs for back-compat)
if run_button or "results" not in st.session_state:
    with st.spinner(f"Running {rounds} rounds with {provider}/{model}..."):
        random.seed(seed)
        results = run_redteam(
            rounds=rounds,
            target_provider=provider,
            target_model=model,
            max_cost_usd=max_cost_usd,
        )
        st.session_state["results"] = results
        st.session_state["seed"] = seed
        st.session_state["provider"] = provider
        st.session_state["model"] = model

results = st.session_state.get("results", {})

if results:
    st.markdown("## 📊 Results")
    target_info = results.get("target", {})
    st.markdown(
        f"**Rounds:** {results['total_rounds']}  •  **Seed:** {st.session_state.get('seed', '?')}  "
        f"•  **Target:** {target_info.get('provider', '?')} / {target_info.get('model', '?')}"
    )

    # Top metrics
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Executed", results.get("attacks_executed", 0))
    m2.metric("Blocked", results.get("attacks_blocked", 0),
              delta=f"{results.get('block_rate', 0)*100:.1f}%",
              delta_color="inverse")
    m3.metric("Succeeded", results.get("attacks_succeeded", 0))
    m4.metric("Cost", f"${results.get('total_cost_usd', 0):.4f}")
    m5.metric("Tokens", f"{results.get('total_input_tokens', 0)+results.get('total_output_tokens', 0):,}")
    m6.metric("Elapsed", f"{results.get('elapsed_seconds', 0):.2f}s")

    st.markdown("---")

    # Two columns: block rate by layer + per-attack results
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### 🛡️ Block Rate by Defense Layer")
        layer_data = results.get("block_rate_by_layer", {})
        total = results.get("attacks_executed", 1)
        # Display as bar chart
        if layer_data:
            st.bar_chart({name: count for name, count in layer_data.items()})

    with col_right:
        st.markdown("### 🎯 Per-Attack Success Rate")
        per_attack = results.get("results_by_attack", {})
        if per_attack:
            for attack_name, stats in per_attack.items():
                attempted = stats.get("attempted", 0)
                succeeded = stats.get("succeeded", 0)
                success_rate = (succeeded / attempted * 100) if attempted else 0
                st.progress(success_rate / 100, text=f"{attack_name}: {succeeded}/{attempted} succeeded ({success_rate:.0f}%)")

    st.markdown("---")

    # Defense latency
    st.markdown("### ⏱️ Defense Layer Latency (avg ms)")
    latency = results.get("avg_defense_latency_ms", {})
    if latency:
        st.bar_chart(latency)

    # v0.2: Cost panel (only meaningful for non-mock providers)
    if results.get("total_cost_usd", 0) > 0 or provider != "mock":
        st.markdown("---")
        st.markdown("### 💰 Cost & Token Usage")
        cost_c1, cost_c2, cost_c3 = st.columns(3)
        cost_c1.metric("Total Cost (USD)", f"${results.get('total_cost_usd', 0):.4f}")
        cost_c2.metric("Input Tokens", f"{results.get('total_input_tokens', 0):,}")
        cost_c3.metric("Output Tokens", f"{results.get('total_output_tokens', 0):,}")

    st.markdown("---")

    # Detailed JSON (collapsible)
    with st.expander("📋 View raw JSON output"):
        st.json(results)

# Footer
st.markdown("---")
st.markdown("""
**About this dashboard**

This is the companion Streamlit dashboard for the Agent Red Team Platform
(F:/Research/projects/agent_redteam/), developed as a companion artifact to
the survey §8 "Theme 6 — Security: Prompt Injection and Red-Team Attacks".

- [Survey §8](F:/Research/PAPER_SURVEY/llm_agent_calibration_survey.md#8-theme-6--security-prompt-injection-and-red-team-attacks)
- [Attack Taxonomy (12 vectors)](F:/Research/projects/agent_redteam/data/attack_vectors.json)
- [Source Code](F:/Research/projects/agent_redteam/scripts/run_redteam.py)

Anonymous Authors (TMLR double-blind compliant).
""")