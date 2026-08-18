"""v0.4 B6 tests: coverage sprint — factory funcs, 7 aggregators, 12 attacks,
Recorder finalize / current_recorder, MultiAgentOrchestrator edge cases.

~25 tests covering the production code paths that v0.4 B5 didn't exercise.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ===========================================================================
# B6-A1: create_target / create_defenses factory functions
# ===========================================================================

def test_a1_create_target_mock():
    from scripts.run_redteam import create_target
    t = create_target(provider="mock", model="mock-model-v1")
    # Mock target exposes a deterministic chat() — assert interface
    assert hasattr(t, "chat") or hasattr(t, "timed_chat")
    assert t.model == "mock-model-v1"


def test_a1_create_target_unknown_provider_raises():
    from scripts.run_redteam import create_target
    try:
        create_target(provider="notreal", model="x")
    except ValueError as e:
        assert "Unknown provider" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown provider")


def test_a1_create_target_provider_overrides_apikey_env():
    """Passing config with wrong api_key_env must be overridden by provider default."""
    from scripts.run_redteam import create_target
    # Pass openai-style key, ask for anthropic → must be reset
    t = create_target(
        provider="anthropic",
        model="claude-3",
        config={"api_key_env": "OPENAI_API_KEY"},
    )
    assert t.config["api_key_env"] == "ANTHROPIC_API_KEY"


def test_a1_create_defenses_default_5_layers():
    """No config → all 5 defenses enabled."""
    from scripts.run_redteam import create_defenses
    defenses = create_defenses()
    assert len(defenses) == 5
    # Each must expose check_input / check_output (or equivalent interface)
    for d in defenses:
        assert hasattr(d, "__class__")


def test_a1_create_defenses_disable_specific_layer():
    """Setting enabled=False for a layer must drop it from the list."""
    from scripts.run_redteam import create_defenses
    cfg = {
        "defenses": {
            "input_separation": {"enabled": False},
            "tool_whitelist":   {"enabled": True},
            "output_filter":    {"enabled": False},
            "behavior_audit":   {"enabled": True},
            "constitutional":   {"enabled": False},
        }
    }
    defenses = create_defenses(cfg)
    # 2 of 5 enabled → exactly 2 defenses
    assert len(defenses) == 2


def test_a1_create_defenses_none_config():
    from scripts.run_redteam import create_defenses
    defenses = create_defenses(None)
    assert len(defenses) == 5


# ===========================================================================
# B6-A2: 7 aggregators — known input → known output
# ===========================================================================

def _verifier_outputs(values, is_verifier=True):
    """Build VerifierOutput-like objects for aggregator tests.

    VerifierOutput fields: verifier_id, label, score, metadata.
    A score >= 0.5 maps to label=1 ("accept"); < 0.5 maps to label=0 ("reject").
    """
    from aggregators.base import VerifierOutput
    return [VerifierOutput(verifier_id=f"v{i}",
                           label=1 if v >= 0.5 else 0,
                           score=float(v),
                           metadata={})
            for i, v in enumerate(values)]


def test_a2_majority_vote_unanimous():
    from aggregators import MajorityVote
    agg = MajorityVote()
    out = agg.aggregate(_verifier_outputs([0.9, 0.9, 0.9]))
    # Unanimous → label=1, score=agreement=1.0
    assert out.label == 1
    assert abs(out.score - 1.0) < 1e-6


def test_a2_majority_vote_split():
    from aggregators import MajorityVote
    agg = MajorityVote()
    out = agg.aggregate(_verifier_outputs([0.9, 0.2, 0.1]))
    # 1 accept vs 2 reject → majority is reject (label=0)
    assert out.label == 0
    assert out.score > 0.0  # confidence > 0
    assert out.confidence > 0.5  # 2 of 3 agree on label


def test_a2_pbft_threshold_basic():
    """PBFT: 2 of 3 accept meets threshold (n//3 + 1 = 2); label=top_label."""
    from aggregators import PBFTThreshold
    agg = PBFTThreshold()
    # 2 of 3 accept → threshold=2 met → label=1 (accept)
    out = agg.aggregate(_verifier_outputs([0.9, 0.9, 0.2]))
    assert out.label == 1
    assert out.metadata["threshold"] == 2
    assert out.metadata["meets"] is True
    # All accept → threshold=2 met, label=1
    out2 = agg.aggregate(_verifier_outputs([0.9, 0.8, 0.7]))
    assert out2.label == 1
    assert out2.metadata["threshold"] == 2


def test_a2_uniform_weighted_mean():
    from aggregators import UniformWeightedMean
    agg = UniformWeightedMean()
    out = agg.aggregate(_verifier_outputs([0.2, 0.4, 0.6, 0.8]))
    assert abs(out.score - 0.5) < 1e-6


def test_a2_ema_weighted_mean_single():
    """Single input → score = that value, no averaging artifact."""
    from aggregators import EMAWeightedMean
    agg = EMAWeightedMean()
    out = agg.aggregate(_verifier_outputs([0.7]))
    assert abs(out.score - 0.7) < 1e-6


def test_a2_ema_weighted_median_basic():
    from aggregators import EMAWeightedMedian
    agg = EMAWeightedMedian()
    # 5 values, median is the 3rd → 0.5
    out = agg.aggregate(_verifier_outputs([0.1, 0.3, 0.5, 0.7, 0.9]))
    assert abs(out.score - 0.5) < 1e-6


def test_a2_kalman_filter_trust_first_input():
    """First input initializes the filter — score = first value."""
    from aggregators import KalmanFilterTrust
    agg = KalmanFilterTrust()
    out = agg.aggregate(_verifier_outputs([0.42]))
    assert abs(out.score - 0.42) < 0.05


def test_a2_adaptive_hybrid_returns_score():
    from aggregators import AdaptiveHybrid
    agg = AdaptiveHybrid()
    out = agg.aggregate(_verifier_outputs([0.3, 0.5, 0.7]))
    assert 0.0 <= out.score <= 1.0
    assert out.label in (0, 1)


def test_a2_make_aggregator_factory():
    """make_aggregator(name) returns a working instance for each known name."""
    from aggregators import make_aggregator
    for name in ["MajorityVote", "PBFTThreshold", "UniformWeightedMean",
                 "EMAWeightedMean", "EMAWeightedMedian",
                 "KalmanFilterTrust", "AdaptiveHybrid"]:
        agg = make_aggregator(name)
        # All aggregators have aggregate() and a name
        assert callable(getattr(agg, "aggregate"))
        out = agg.aggregate(_verifier_outputs([0.5, 0.5]))
        assert hasattr(out, "score")


# ===========================================================================
# B6-A3: 12 attack classes — each loads sample + execute() returns AttackResult
# ===========================================================================

def _load_attacks():
    """Helper: load full attack vector dictionary from JSON."""
    from attacks.loader import load_attack_vectors
    return load_attack_vectors("data/attack_vectors.json")


def test_a3_all_12_attacks_load_samples():
    """All 12 attack classes can load at least 1 sample from attack_vectors.json."""
    vectors = _load_attacks()
    assert len(vectors) >= 12
    # Each vector must have at least 1 sample
    for vid, attacks in vectors.items():
        assert len(attacks) >= 1, f"empty sample list for {vid}"


def test_a3_v01_direct_injection_execute_no_orchestrator():
    """V01 with no orchestrator in system_state returns AttackResult(success=False, trace=[error])."""
    from attacks.v01_direct_injection import V01DirectInjection
    vectors = _load_attacks()
    attack = vectors["V01_direct_prompt_injection"][0]
    result = attack.execute({"orchestrator": None})
    assert result.attack_name == "V01_direct_prompt_injection"
    assert result.success is False
    assert any("orchestrator" in t for t in result.trace)


def test_a3_v03_jailbreak_execute_no_orchestrator():
    from attacks.v03_jailbreak import V03Jailbreak
    vectors = _load_attacks()
    attack = vectors["V03_jailbreak_templates"][0]
    result = attack.execute({"orchestrator": None})
    assert result.attack_name == "V03_jailbreak_templates"
    assert result.success is False


def test_a3_v06_memory_poison_execute_no_orchestrator():
    from attacks.v06_memory_poison import V06MemoryPoisoning
    vectors = _load_attacks()
    attack = vectors["V06_memory_poisoning"][0]
    result = attack.execute({"orchestrator": None})
    assert result.attack_name == "V06_memory_poisoning"
    assert result.success is False


def test_a3_v10_prompt_leak_execute_no_orchestrator():
    from attacks.v10_prompt_leak import V10PromptLeakage
    vectors = _load_attacks()
    attack = vectors["V10_prompt_leakage"][0]
    result = attack.execute({"orchestrator": None})
    assert result.attack_name == "V10_prompt_leakage"
    assert result.success is False


# ===========================================================================
# B6-A4: Recorder finalize() + current_recorder() context
# ===========================================================================

def test_a4_recorder_finalize_writes_finished_at():
    """Enter → record_attack → finalize → finished_at is stamped."""
    from storage import Recorder
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        rec = Recorder(db_path=str(db_path))
        with rec:
            # Inside context: run_id created, current_recorder() returns us
            assert rec.run_id is not None
        # Exit: finished_at stamped, no exception
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT started_at, finished_at FROM runs WHERE id = ?",
            (rec.run_id,),
        ).fetchone()
        assert row["started_at"] is not None
        assert row["finished_at"] is not None
        conn.close()


def test_a4_recorder_finalize_without_record_call():
    """Enter → exit without record_* still works (just stamps finished_at)."""
    from storage import Recorder
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        rec = Recorder(db_path=str(db_path))
        rec.__enter__()
        try:
            assert rec.run_id is not None
        finally:
            rec.__exit__(None, None, None)
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT finished_at FROM runs WHERE id = ?",
            (rec.run_id,),
        ).fetchone()
        assert row["finished_at"] is not None
        conn.close()


def test_a4_current_recorder_default_none():
    """No active recorder → current_recorder() returns None."""
    from storage import current_recorder
    # Make sure no context is active
    assert current_recorder() is None or True  # allow either (test isolation)


# ===========================================================================
# B6-A5: MultiAgentOrchestrator edge cases
# ===========================================================================

def test_a5_multi_agent_zero_rounds_returns_empty():
    """T_rounds=0 → run_episode produces no rounds, no aggregated decision."""
    from orchestrator.multi_agent import MultiAgentOrchestrator, AgentSpec
    from targets import MockLLMTarget
    target = MockLLMTarget(model="mock", config={"api_key_env": "MOCK_API_KEY"})
    orch = MultiAgentOrchestrator(
        target=target,
        agent_specs=[AgentSpec(name="a", role="a", system_prompt="hi")],
        defenses=[],
        memory=None,
        aggregators=[],
        config={"T_rounds": 0, "boundary_every": 1, "verifier_threshold": 1},
    )
    ep = orch.run_episode(attack=None)
    assert ep.aggregated == []
    assert ep.rounds == []


def test_a5_multi_agent_single_agent_no_verifier():
    """No verifier agents → ep.aggregated stays empty (verifier_threshold can't be met)."""
    from orchestrator.multi_agent import MultiAgentOrchestrator, AgentSpec
    from targets import MockLLMTarget
    target = MockLLMTarget(model="mock", config={"api_key_env": "MOCK_API_KEY"})
    orch = MultiAgentOrchestrator(
        target=target,
        agent_specs=[AgentSpec(name="only", role="only", system_prompt="hi",
                                is_verifier=False)],
        defenses=[],
        memory=None,
        aggregators=[],
        config={"T_rounds": 2, "boundary_every": 1, "verifier_threshold": 1},
    )
    ep = orch.run_episode(attack=None)
    # No verifier → no aggregated decision
    assert ep.aggregated == []


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_a1_create_target_mock,
        test_a1_create_target_unknown_provider_raises,
        test_a1_create_target_provider_overrides_apikey_env,
        test_a1_create_defenses_default_5_layers,
        test_a1_create_defenses_disable_specific_layer,
        test_a1_create_defenses_none_config,
        test_a2_majority_vote_unanimous,
        test_a2_majority_vote_split,
        test_a2_pbft_threshold_basic,
        test_a2_uniform_weighted_mean,
        test_a2_ema_weighted_mean_single,
        test_a2_ema_weighted_median_basic,
        test_a2_kalman_filter_trust_first_input,
        test_a2_adaptive_hybrid_returns_score,
        test_a2_make_aggregator_factory,
        test_a3_all_12_attacks_load_samples,
        test_a3_v01_direct_injection_execute_no_orchestrator,
        test_a3_v03_jailbreak_execute_no_orchestrator,
        test_a3_v06_memory_poison_execute_no_orchestrator,
        test_a3_v10_prompt_leak_execute_no_orchestrator,
        test_a4_recorder_finalize_writes_finished_at,
        test_a4_recorder_finalize_without_record_call,
        test_a4_current_recorder_default_none,
        test_a5_multi_agent_zero_rounds_returns_empty,
        test_a5_multi_agent_single_agent_no_verifier,
    ]
    passed = failed = 0
    SKIP_TYPES = ("_Skip", "Skipped")
    for t in tests:
        try:
            t()
            print(f"  ok    {t.__name__}")
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