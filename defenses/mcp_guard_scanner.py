"""McpGuardScannerDefense — 把 mcp-guard（相邻仓）的投毒规则轴 + 能力分层轴
接入本仓防御管线（v0.5 R6）。

设计边界：
- 跨仓加载走 importlib 探测 checkout（config > env MCP_GUARD_REPO > ../mcp-guard），
  与 auditable-llm-eval 的 trace.py 同一模式；不依赖 ambient sys.modules。
- 引擎不可用时 FLAG（放行但留痕 audit），不静默 ALLOW——诚实声明"这层没评"。
- 投毒命中 → BLOCK；能力分层只记录（tier/dangerous 参数进 metadata），
  注解说谎（readOnlyHint=true 但能力轴判 T3）→ FLAG。
- 本层是词法/规则启发式，不声明检出率；unknown 保持 unknown。
"""
from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Defense, DefenseAction, DefenseResult

_DEFAULT_NEIGHBOUR = Path(__file__).resolve().parents[2] / "mcp-guard"


def _load_guard(repo: Path) -> Optional[dict]:
    """从 mcp-guard checkout 动态加载 guard.rules / guard.capability / guard.scan。

    返回 {"rules": module, "capability": module, "scan": module} 或 None。
    """
    if not (repo / "guard" / "capability.py").exists():
        return None
    try:
        spec_r = importlib.util.spec_from_file_location(
            "_mcp_guard_rules", repo / "guard" / "rules.py")
        rules = importlib.util.module_from_spec(spec_r)
        spec_r.loader.exec_module(rules)
        spec_c = importlib.util.spec_from_file_location(
            "_mcp_guard_capability", str(repo / "guard" / "capability.py"))
        capability = importlib.util.module_from_spec(spec_c)
        spec_c.loader.exec_module(capability)
        return {"rules": rules, "capability": capability}
    except Exception:
        return None


class McpGuardScannerDefense(Defense):
    name = "mcp_guard_scanner"
    layer_index = 6   # input_separation(1) → tool_whitelist(2) → output_filter(3) →
                      # behavior_audit(4) → constitutional(5) → mcp_guard(6)
    description = ("mcp-guard 跨仓扫描：工具描述投毒规则命中 → BLOCK；"
                   "能力分层与注解错配 → FLAG（默认只记录 tier）")

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        cfg = self.config or {}
        repo = Path(cfg.get("mcp_guard_repo")
                    or os.environ.get("MCP_GUARD_REPO")
                    or _DEFAULT_NEIGHBOUR)
        self._guard = _load_guard(repo)
        self._repo = str(repo)

    def check(self, event: Dict[str, Any]) -> DefenseResult:
        start = time.time()
        trace: List[str] = [f"[{self.name}] check() called (layer {self.layer_index})"]
        tool = event.get("tool", "")
        description = event.get("description", "") or ""

        if self._guard is None:
            trace.append(f"[{self.name}] engine unavailable (repo={self._repo}) — FLAG, not assessing")
            return self._result(DefenseAction.FLAG,
                                reason="mcp-guard engine unavailable — tool surface NOT scanned (audit trail kept)",
                                trace=trace, start=start,
                                metadata={"engine": "unavailable", "repo": self._repo,
                                          "rule_ids": [], "tier": None})

        rules = self._guard["rules"]
        capability = self._guard["capability"]

        # 轴一：投毒规则（描述文本 + schema 合成文本，与 mcp-guard scan_tool 同一入口）
        tool_surface = {"name": tool, "description": description,
                        "inputSchema": event.get("inputSchema"),
                        "annotations": event.get("annotations")}
        hits = rules.scan_text(description) if description else []
        rule_ids = sorted({h["rule"] for h in hits})
        trace.append(f"[{self.name}] poison rules: {rule_ids or 'no hits'}")

        # 轴二：能力分层（name/description/schema 证据；unknown 保持 unknown）
        cap = capability.scan_capability(tool_surface)
        tier = cap.get("tier")
        trace.append(f"[{self.name}] capability tier: {tier} (unknown={cap.get('unknown')})")

        if rule_ids:
            return self._result(
                DefenseAction.BLOCK,
                reason=f"tool description matched poisoned rule(s): {', '.join(rule_ids)}",
                trace=trace, start=start,
                metadata={"engine": "loaded", "repo": self._repo,
                          "rule_ids": rule_ids, "tier": tier,
                          "capability_unknown": bool(cap.get("unknown"))})

        # 注解说谎：自称只读（readOnlyHint=true）但能力轴按 schema/描述证据判到 T3
        annotations = event.get("annotations") or {}
        if annotations.get("readOnlyHint") is True and tier == capability.T3_DESTRUCTIVE:
            return self._result(
                DefenseAction.FLAG,
                reason=f"annotation claims read-only but capability axis tiers it {tier}",
                trace=trace, start=start,
                metadata={"engine": "loaded", "repo": self._repo,
                          "rule_ids": [], "tier": tier,
                          "capability_unknown": False,
                          "mismatch": "read-only-annotation-vs-T3"})

        return self._result(
            DefenseAction.ALLOW,
            reason=f"no poison hits; capability tier {tier}",
            trace=trace, start=start,
            metadata={"engine": "loaded", "repo": self._repo,
                      "rule_ids": [], "tier": tier,
                      "capability_unknown": bool(cap.get("unknown"))})

    def _result(self, action, reason, trace, start, metadata) -> DefenseResult:
        return DefenseResult(
            defense_name=self.name, action=action, reason=reason,
            confidence=1.0, trace=trace,
            elapsed_ms=(time.time() - start) * 1000, metadata=metadata)
