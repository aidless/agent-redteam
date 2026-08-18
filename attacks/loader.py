"""Attack loader — read attack_vectors.json and materialise Attack objects.

Usage:
    attacks = load_attack_vectors("data/attack_vectors.json")
    attack = attacks["V01_direct_prompt_injection"][0]
    result = attack.execute({"orchestrator": orch, "memory": mem, ...})

The loader is intentionally tiny — it returns a dict keyed by
vector_id, each entry a list of Attack instances. The orchestrator can
then iterate or pick.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import Attack, AttackResult, AttackSeverity
from .v01_direct_injection import V01DirectInjection
from .v02_indirect_injection import V02IndirectInjection
from .v03_jailbreak import V03Jailbreak
from .v04_role_hijack import V04RoleHijack
from .v05_tool_redirect import V05ToolRedirect
from .v06_memory_poison import V06MemoryPoisoning
from .v07_output_exfil import V07OutputExfil
from .v08_aggregator_capture import V08AggregatorCapture
from .v09_sybil_agent import V09SybilAgent
from .v10_prompt_leak import V10PromptLeakage
from .v11_resource_exhaustion import V11ResourceExhaustion
from .v12_compositional import V12Compositional


# Map vector_id -> (class, category, default_severity)
VECTOR_REGISTRY: Dict[str, Any] = {
    "V01_direct_prompt_injection":     (V01DirectInjection,        "input_attack", AttackSeverity.HIGH),
    "V02_indirect_prompt_injection":   (V02IndirectInjection,      "input_attack", AttackSeverity.HIGH),
    "V03_jailbreak_templates":         (V03Jailbreak,              "input_attack", AttackSeverity.HIGH),
    "V04_role_hijack":                 (V04RoleHijack,             "input_attack", AttackSeverity.MEDIUM),
    "V05_tool_call_redirection":       (V05ToolRedirect,           "tool_attack",  AttackSeverity.HIGH),
    "V06_memory_poisoning":            (V06MemoryPoisoning,        "memory_attack",AttackSeverity.HIGH),
    "V07_output_exfiltration":         (V07OutputExfil,            "output_attack",AttackSeverity.MEDIUM),
    "V08_aggregator_capture":          (V08AggregatorCapture,      "comm_attack",  AttackSeverity.CRITICAL),
    "V09_sybil_agent":                 (V09SybilAgent,             "comm_attack",  AttackSeverity.HIGH),
    "V10_prompt_leakage":              (V10PromptLeakage,          "input_attack", AttackSeverity.MEDIUM),
    "V11_resource_exhaustion":         (V11ResourceExhaustion,     "input_attack", AttackSeverity.MEDIUM),
    "V12_compositional":               (V12Compositional,          "composite",    AttackSeverity.CRITICAL),
}


def _build_attack(vector_id: str, sample: Dict[str, Any], category: str,
                  default_severity: AttackSeverity) -> Attack:
    cls, cat, sev = VECTOR_REGISTRY[vector_id]
    return cls(sample=sample, category=category, severity=sev)


def load_attack_vectors(
    path: str,
    only: Optional[List[str]] = None,
) -> Dict[str, List[Attack]]:
    """Load attack vectors from JSON.

    Parameters
    ----------
    path  : path to attack_vectors.json
    only  : optional whitelist of vector_ids to load

    Returns
    -------
    dict mapping vector_id -> list of Attack instances
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, List[Attack]] = {}
    for vec in data.get("attack_vectors", []):
        vid = vec["vector_id"]
        if only is not None and vid not in only:
            continue
        if vid not in VECTOR_REGISTRY:
            continue
        attacks = [
            _build_attack(vid, s, vec.get("category", "input_attack"),
                          _parse_severity(vec.get("severity", "medium")))
            for s in vec.get("samples", [])
        ]
        out[vid] = attacks
    return out


def _parse_severity(s: str) -> AttackSeverity:
    return {
        "info": AttackSeverity.INFO,
        "low": AttackSeverity.LOW,
        "medium": AttackSeverity.MEDIUM,
        "high": AttackSeverity.HIGH,
        "critical": AttackSeverity.CRITICAL,
    }.get(s.lower(), AttackSeverity.MEDIUM)


def all_vector_ids() -> List[str]:
    """Return the canonical list of 12 vector_ids in registry order."""
    return list(VECTOR_REGISTRY.keys())


def make_attack(vector_id: str, sample: Dict[str, Any]) -> Attack:
    """Build a single Attack from a sample dict (no JSON loading)."""
    if vector_id not in VECTOR_REGISTRY:
        raise KeyError(f"Unknown vector_id: {vector_id}")
    cls, cat, sev = VECTOR_REGISTRY[vector_id]
    return cls(sample=sample, category=cat, severity=sev)