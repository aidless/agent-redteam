"""Layer 2: Tool-Call Whitelist.

Validates every tool/function call against an allow-list of permitted tools
and argument constraints. Blocks calls to unauthorized tools or tools with
suspicious arguments (path traversal, SQL injection, RCE patterns).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .base import Defense, DefenseAction, DefenseResult


class ToolWhitelistDefense(Defense):
    """Defends against tool-call redirection (V05) and path/RCE attacks.

    Strategy:
        - Each agent has a whitelist of permitted tools.
        - Each tool has a whitelist of permitted argument patterns.
        - Suspicious argument patterns (path traversal, shell metachars,
          SQL keywords) trigger BLOCK regardless of tool whitelist.

    Configuration:
        agent_tool_whitelist: Dict[agent_name, List[str]]
        dangerous_arg_patterns: regex patterns for suspicious arguments
    """

    name = "tool_whitelist"
    layer_index = 2
    description = "Allow-list for tool calls + argument validation"

    DEFAULT_DANGEROUS_PATTERNS = [
        r"\.\./\.\./",                          # Path traversal
        r"/etc/(?:passwd|shadow|hosts)",        # System files
        r"\$\(.*?\)",                            # Command substitution
        r"`.*?`",                                # Backtick execution
        r";\s*(?:rm|wget|curl|chmod|chown)",   # Shell injection
        r"\b(?:DROP|TRUNCATE|DELETE\s+FROM)\b",  # SQL destructive
        r"\bUNION\s+SELECT\b",                   # SQL injection
        r"\beval\s*\(",                          # Python eval
        r"\bexec\s*\(",                          # Python exec
        r"\bos\.system\s*\(",                    # Python os.system
        r"\bsubprocess\.",                       # Python subprocess
    ]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.agent_tool_whitelist: Dict[str, List[str]] = self.config.get(
            "agent_tool_whitelist",
            {
                "default": ["search", "read_file", "summarize"],
                "code_executor": ["execute_python", "execute_bash"],
                "email_assistant": ["send_email", "read_email"],
                "data_analyst": ["db_query", "read_file"],
            },
        )
        self.dangerous_regex = re.compile(
            "|".join(self.config.get("dangerous_arg_patterns", self.DEFAULT_DANGEROUS_PATTERNS))
        )

    def check(self, event: Dict[str, Any]) -> DefenseResult:
        """Check a tool-call event.

        Args:
            event: Must contain 'agent' (str), 'tool' (str), 'args' (dict).

        Returns:
            DefenseResult.
        """
        import time
        start = time.time()

        agent = event.get("agent", "default")
        tool = event.get("tool", "")
        args = event.get("args", {})

        trace = [f"[tool_whitelist] agent={agent}, tool={tool}"]

        # Check tool whitelist
        allowed_tools = self.agent_tool_whitelist.get(agent, self.agent_tool_whitelist.get("default", []))
        if tool not in allowed_tools:
            elapsed = (time.time() - start) * 1000
            trace.append(f"[tool_whitelist] BLOCK: tool '{tool}' not in whitelist for agent '{agent}'")
            return DefenseResult(
                defense_name=self.name,
                action=DefenseAction.BLOCK,
                reason=f"Tool '{tool}' not permitted for agent '{agent}'",
                confidence=0.95,
                trace=trace,
                elapsed_ms=elapsed,
                metadata={"agent": agent, "tool": tool, "allowed": allowed_tools},
            )

        # Check dangerous argument patterns
        args_str = str(args)
        match = self.dangerous_regex.search(args_str)
        if match:
            elapsed = (time.time() - start) * 1000
            trace.append(f"[tool_whitelist] BLOCK: dangerous arg pattern: {match.group()}")
            return DefenseResult(
                defense_name=self.name,
                action=DefenseAction.BLOCK,
                reason=f"Dangerous argument pattern detected: '{match.group()}'",
                confidence=0.92,
                trace=trace,
                elapsed_ms=elapsed,
                metadata={"matched_pattern": match.group(), "tool": tool, "agent": agent},
            )

        # Path traversal / endpoint check
        for arg_name, arg_value in args.items():
            if isinstance(arg_value, str):
                if "endpoint" in arg_name.lower() or "url" in arg_name.lower():
                    if not self._is_internal_endpoint(arg_value):
                        elapsed = (time.time() - start) * 1000
                        trace.append(f"[tool_whitelist] BLOCK: external endpoint '{arg_value}'")
                        return DefenseResult(
                            defense_name=self.name,
                            action=DefenseAction.BLOCK,
                            reason=f"External endpoint not permitted: {arg_value}",
                            confidence=0.93,
                            trace=trace,
                            elapsed_ms=elapsed,
                        )

        # All checks passed
        elapsed = (time.time() - start) * 1000
        return DefenseResult(
            defense_name=self.name,
            action=DefenseAction.ALLOW,
            reason=f"Tool '{tool}' allowed for agent '{agent}'",
            confidence=0.90,
            trace=trace,
            elapsed_ms=elapsed,
        )

    def _is_internal_endpoint(self, url: str) -> bool:
        """Check if URL is internal (no external HTTP)."""
        internal_hosts = self.config.get("internal_hosts", ["localhost", "127.0.0.1", "internal.api"])
        return any(host in url for host in internal_hosts) or not url.startswith(("http://", "https://"))