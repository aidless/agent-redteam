"""v0.3 smoke tests for the Agent Red Team Platform.

These tests cover the 6 v0.3 additions:
- A3 metrics (calibration)
- A4 memory (3 architectures)
- A5 aggregators (7 implementations)
- A1 attacks (12 vector loaders + 1 sample execution)
- A2 multi-agent orchestrator (1 episode)
- A6 tradeoff module (Pareto + GSM8K proxy shape)

Run with:
    .venv/Scripts/python.exe -m pytest tests/test_v03.py -v
or directly:
    .venv/Scripts/python.exe tests/test_v03.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# Make project root importable when running from any CWD
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# A3: metrics
# ---------------------------------------------------------------------------

def test_metrics_ece():
    from metrics import ece
    # perfect alignment
    assert ece([0.0, 1.0], [0, 1], 15) == 0.0
    # over-confident wrong
    assert ece([0.9, 0.9], [0, 0], 15) > 0.8
    # empty
    assert ece([], [], 15) == 0.0


def test_metrics_jsd_entropy():
    from metrics import jsd, entropy
    assert jsd([0.5, 0.5], [0.5, 0.5]) < 1e-9
    assert jsd([1, 0], [0, 1]) > 0.99
    assert abs(entropy([1, 1, 1, 1]) - 1.0) < 1e-9
    assert abs(entropy([1, 0, 0, 0]) - 0.0) < 1e-9


def test_metrics_cv_and_gamma():
    from metrics import cv, gamma_temporal, coupling
    assert cv([3, 3, 3]) == 0.0
    assert cv([0, 0, 0]) == 0.0
    assert cv([-1, 0, 1]) == float("inf")
    assert cv([1, 2, 3]) > 0
    # Wasserstein-1
    assert gamma_temporal([1, 2, 3, 4], [1, 2, 3, 4]) == 0.0
    assert gamma_temporal([1, 2, 3, 4], [2, 3, 4, 5]) > 0
    assert gamma_temporal([], []) == 0.0
    # coupling
    assert coupling([1, 0, 0], [1, 0, 0]) == 0.0
    assert abs(coupling([0, 1], [1, 0]) - math.sqrt(2)) < 1e-9


def test_metrics_impossibility_triangle():
    from metrics import impossibility_triangle
    r = impossibility_triangle(0.0, 0.0, 0.0, c_min=1e-3)
    assert r.violated
    r2 = impossibility_triangle(2.0, 0.5, 2.0, c_min=1e-3)
    assert not r2.violated
    assert r2.passes


# ---------------------------------------------------------------------------
# A4: memory
# ---------------------------------------------------------------------------

def test_memory_append_only():
    from memory import AppendOnlyMemory, MemoryEntry
    am = AppendOnlyMemory()
    for i in range(7):
        am.add(MemoryEntry(content=f"e{i}", round=i))
    assert len(am) == 7
    last3 = am.retrieve("anything", k=3)
    assert [e.content for e in last3] == ["e6", "e5", "e4"]
    am.reset()
    assert len(am) == 0


def test_memory_summarization():
    from memory import SummarizationMemory, MemoryEntry
    from targets import MockLLMTarget
    sm = SummarizationMemory(target=MockLLMTarget(),
                             summarize_every=3, keep_last=1)
    for i in range(5):
        sm.add(MemoryEntry(content=f"line {i}", round=i))
    assert any(e.role == "summary" for e in sm._summaries)
    sm.reset()
    assert len(sm) == 0
    # Fallback path without target
    sm2 = SummarizationMemory(target=None, summarize_every=2, keep_last=1)
    for i in range(3):
        sm2.add(MemoryEntry(content="x", round=i))
    assert any("fallback" in (e.content if isinstance(e.content, str) else "")
               for e in sm2._summaries)


def test_memory_rag():
    from memory import RAGMemory, MemoryEntry
    rm = RAGMemory()
    rm.add(MemoryEntry(content="prompt injection attack"))
    rm.add(MemoryEntry(content="jailbreak template"))
    rm.add(MemoryEntry(content="memory poisoning"))
    top = rm.retrieve("jailbreak", k=1)
    assert top[0].content.startswith("jailbreak")
    assert rm.retrieve("zzz", k=3)[0] is not None
    assert len(rm) == 3
    assert RAGMemory().retrieve("x", k=5) == []


# ---------------------------------------------------------------------------
# A5: aggregators
# ---------------------------------------------------------------------------

def _v(items):
    from aggregators import VerifierOutput
    return [VerifierOutput(verifier_id=v[0], label=v[1], score=v[2]) for v in items]


def test_aggregators_all_seven():
    from aggregators import (
        MajorityVote, PBFTThreshold, UniformWeightedMean,
        EMAWeightedMean, EMAWeightedMedian, KalmanFilterTrust, AdaptiveHybrid,
    )
    items = _v([("a", 1, 0.9), ("b", 1, 0.7), ("c", 0, 0.3)])
    for cls in [MajorityVote, PBFTThreshold, UniformWeightedMean,
                EMAWeightedMean, EMAWeightedMedian, KalmanFilterTrust, AdaptiveHybrid]:
        d = cls().aggregate(items)
        assert d.label in (0, 1)
        assert 0.0 <= d.score <= 1.0
        assert 0.0 <= d.confidence <= 1.0


def test_aggregators_registry():
    from aggregators import AGGREGATOR_REGISTRY, make_aggregator
    assert len(AGGREGATOR_REGISTRY) == 7
    a = make_aggregator("KalmanFilterTrust", process_var=0.05, meas_var=0.2)
    assert a.process_var == 0.05
    try:
        make_aggregator("Nonexistent")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown aggregator")


def test_aggregators_empty_input():
    from aggregators import (
        MajorityVote, PBFTThreshold, UniformWeightedMean,
        EMAWeightedMean, EMAWeightedMedian, KalmanFilterTrust, AdaptiveHybrid,
    )
    for cls in [MajorityVote, PBFTThreshold, UniformWeightedMean,
                EMAWeightedMean, EMAWeightedMedian, KalmanFilterTrust, AdaptiveHybrid]:
        d = cls().aggregate([])
        assert d.label == 0 and d.score == 0.0


# ---------------------------------------------------------------------------
# A1: attacks
# ---------------------------------------------------------------------------

def test_attacks_load_all_12():
    from attacks.loader import load_attack_vectors, all_vector_ids
    avs = load_attack_vectors(str(ROOT / "data" / "attack_vectors.json"))
    assert len(avs) == 12
    assert set(avs) == set(all_vector_ids())
    for vid in all_vector_ids():
        assert len(avs[vid]) >= 1


def test_attacks_execute_v01():
    from attacks.loader import load_attack_vectors
    from orchestrator import SingleAgentOrchestrator
    from targets import MockLLMTarget
    from defenses.base import Defense, DefenseResult, DefenseAction

    class Pass(Defense):
        layer_index = 5
        name = "pass"
        def check(self, *a, **kw):
            return DefenseResult(action=DefenseAction.PASS,
                                  name=self.name, layer_index=self.layer_index)

    target = MockLLMTarget()
    orch = SingleAgentOrchestrator(target=target, defenses=[Pass()],
                                   system_prompt="x")
    avs = load_attack_vectors(str(ROOT / "data" / "attack_vectors.json"))
    res = avs["V01_direct_prompt_injection"][0].execute({"orchestrator": orch})
    assert res.attack_name == "V01_direct_prompt_injection"
    assert res.elapsed_ms >= 0.0


def test_attacks_missing_orchestrator():
    from attacks.loader import load_attack_vectors
    avs = load_attack_vectors(str(ROOT / "data" / "attack_vectors.json"))
    res = avs["V01_direct_prompt_injection"][0].execute({})
    assert res.success is False
    assert "missing" in " ".join(res.trace).lower()


# ---------------------------------------------------------------------------
# A2: multi-agent orchestrator
# ---------------------------------------------------------------------------

def test_multi_agent_episode():
    from orchestrator.multi_agent import (
        MultiAgentOrchestrator, AgentSpec, _default_aggregators,
    )
    from targets import MockLLMTarget
    from defenses.base import Defense, DefenseResult, DefenseAction
    from memory import AppendOnlyMemory

    class Pass(Defense):
        layer_index = 5
        name = "pass"
        def check(self, *a, **kw):
            return DefenseResult(action=DefenseAction.PASS,
                                  name=self.name, layer_index=self.layer_index)

    target = MockLLMTarget()
    specs = [
        AgentSpec("p", "planner", "plan"),
        AgentSpec("v", "verifier", "ver", is_verifier=True),
        AgentSpec("v2", "verifier", "ver2", is_verifier=True),
    ]
    orch = MultiAgentOrchestrator(
        target=target, agent_specs=specs, defenses=[Pass()],
        memory=AppendOnlyMemory(), aggregators=_default_aggregators(),
        config={"T_rounds": 3, "boundary_every": 2},
    )
    class Fake: name = "x"; payload = "hi"; target_agent = "any"
    ep = orch.run_episode(Fake())
    assert len(ep.rounds) == 3
    assert ep.memory_size == 3 * 3   # 3 agents × 3 rounds
    methods = {d.method for d in ep.aggregated}
    assert len(methods) == 7
    assert sum(1 for r in ep.rounds if r["boundary_sync"]) == 1


def test_multi_agent_cost_cap():
    from orchestrator.multi_agent import MultiAgentOrchestrator, AgentSpec
    from targets import MockLLMTarget

    target = MockLLMTarget()
    specs = [AgentSpec("p", "planner", "p")]
    orch = MultiAgentOrchestrator(
        target=target, agent_specs=specs, defenses=[],
        config={"T_rounds": 5, "max_cost_usd": -1.0},
    )
    class Fake: name = "x"; payload = "hi"; target_agent = "any"
    ep = orch.run_episode(Fake())
    assert "max_cost_exceeded" in ep.metadata["reason"]


# ---------------------------------------------------------------------------
# A6: tradeoff
# ---------------------------------------------------------------------------

def test_tradeoff_module_shape():
    from scripts.tradeoff import TradeoffPoint, pareto_front, GSM8K_PROXY
    assert len(GSM8K_PROXY) == 10
    p = TradeoffPoint(0, [], 0.5, 0.3, 0.0, 1.0)
    d = p.to_dict()
    assert d["n_defenses_on"] == 0
    pts = [
        TradeoffPoint(0, [], 0.0, 0.0, 0, 0),
        TradeoffPoint(1, ["a"], 0.5, 0.2, 0, 0),
        TradeoffPoint(2, ["a", "b"], 0.8, 0.5, 0, 0),
        TradeoffPoint(3, ["a", "b", "c"], 0.6, 0.7, 0, 0),
    ]
    front = pareto_front(pts)
    # (0,0,0) is dominated; (0.5,0.2) is dominated by (0.8,0.5);
    # (0.8,0.5) and (0.6,0.7) are on the front
    assert len(front) == 2


def test_tradeoff_run_small():
    from scripts.tradeoff import run_tradeoff
    from targets import MockLLMTarget
    from defenses.input_separation import InputSeparationDefense
    from defenses.output_filter import OutputFilterDefense
    target = MockLLMTarget()
    base = [InputSeparationDefense(), OutputFilterDefense()]
    pts = run_tradeoff(target, base, max_combinations=4)
    assert len(pts) == 4
    for p in pts:
        assert 0.0 <= p.task_utility <= 1.0
        assert 0.0 <= p.block_rate <= 1.0
        assert p.n_defenses_on in (0, 1, 2)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    """Run every test_xxx in this module. Returns 0 on success."""
    import inspect
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