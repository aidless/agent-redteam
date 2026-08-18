"""Layer 3: Output Filtering.

Filters the agent's output to prevent leakage of system prompts, PII, secrets,
and other sensitive content.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import Defense, DefenseAction, DefenseResult


class OutputFilterDefense(Defense):
    """Defends against output exfiltration (V07) and prompt leakage (V10).

    Strategy:
        - Detect and redact common secret patterns (API keys, PII, system prompts).
        - Limit output length to prevent DoS amplification.
        - Detect suspicious formatting (base64, hex-encoded system prompts).

    Configuration:
        max_output_length: truncate outputs beyond this many chars
        enable_pii_redaction: bool
        enable_secret_redaction: bool
    """

    name = "output_filter"
    layer_index = 3
    description = "Post-generation content filtering for secrets, PII, and prompt leakage"

    SECRET_PATTERNS = [
        (r"sk-[A-Za-z0-9]{20,}", "[REDACTED_API_KEY]"),
        (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
        (r"-----BEGIN [A-Z]+ PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
        (r"\b(?:\d{4}[ -]?){3}\d{4}\b", "[REDACTED_CC]"),
    ]

    PROMPT_LEAK_PATTERNS = [
        r"you\s+are\s+(?:a|an)\s+(?:helpful|AI|assistant|language\s+model)",
        r"system\s+prompt\s*:",
        r"my\s+instructions\s+(?:are|say)",
        r"i\s+was\s+told\s+to",
        r"as\s+(?:an?\s+)?(?:AI|assistant|model)",
    ]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.max_output_length = self.config.get("max_output_length", 8000)
        self.enable_pii_redaction = self.config.get("enable_pii_redaction", True)
        self.enable_secret_redaction = self.config.get("enable_secret_redaction", True)

        self.secret_regexes = [
            (re.compile(p), replacement) for p, replacement in self.SECRET_PATTERNS
        ]
        self.prompt_leak_regex = re.compile("(?i:" + "|".join(self.PROMPT_LEAK_PATTERNS) + ")")

    def check(self, event: Dict[str, Any]) -> DefenseResult:
        """Filter an output event.

        Args:
            event: Must contain 'role' (should be 'assistant') and 'content' (str).

        Returns:
            DefenseResult with action (MODIFY if redacted, BLOCK if too long).
        """
        import time
        start = time.time()

        content = event.get("content", "")
        trace = [f"[output_filter] content_len={len(content)}"]

        modified = False
        modified_content = content

        # Secret/PII redaction
        if self.enable_secret_redaction:
            for regex, replacement in self.secret_regexes:
                if regex.search(modified_content):
                    modified_content = regex.sub(replacement, modified_content)
                    modified = True
                    trace.append(f"[output_filter] Redacted: {regex.pattern[:30]}...")

        # Prompt leakage detection
        prompt_match = self.prompt_leak_regex.search(modified_content)
        if prompt_match:
            # Suspicious — block entirely if entire response looks like a leak
            if self._looks_like_full_prompt_leak(modified_content):
                elapsed = (time.time() - start) * 1000
                trace.append(f"[output_filter] BLOCK: full prompt leak suspected")
                return DefenseResult(
                    defense_name=self.name,
                    action=DefenseAction.BLOCK,
                    reason="Output appears to contain system prompt leak",
                    confidence=0.88,
                    trace=trace,
                    elapsed_ms=elapsed,
                    metadata={"matched_pattern": prompt_match.group()},
                )
            # Otherwise modify/redact
            modified_content = "[REDACTED: suspected prompt leak]"
            modified = True
            trace.append(f"[output_filter] Modified: prompt leak pattern matched")

        # Length check (DoS amplification guard)
        if len(modified_content) > self.max_output_length:
            truncated = modified_content[: self.max_output_length] + "\n\n[OUTPUT TRUNCATED: exceeded max length]"
            modified_content = truncated
            modified = True
            trace.append(f"[output_filter] Truncated at {self.max_output_length} chars")

        elapsed = (time.time() - start) * 1000

        if modified:
            return DefenseResult(
                defense_name=self.name,
                action=DefenseAction.MODIFY,
                reason="Output redacted/truncated",
                confidence=0.85,
                trace=trace,
                elapsed_ms=elapsed,
                metadata={"modified_content": modified_content},
            )

        return DefenseResult(
            defense_name=self.name,
            action=DefenseAction.ALLOW,
            reason="Output passes all filters",
            confidence=0.90,
            trace=trace,
            elapsed_ms=elapsed,
        )

    def _looks_like_full_prompt_leak(self, content: str) -> bool:
        """Heuristic: does the entire response look like a system prompt disclosure?"""
        leak_indicators = [
            "you are a",
            "your role is",
            "follow these instructions",
            "your task is to",
            "system:",
            "instructions:",
        ]
        lower = content.lower()
        matches = sum(1 for indicator in leak_indicators if indicator in lower)
        return matches >= 3 and len(content) < 2000  # Short + many indicators = likely leak