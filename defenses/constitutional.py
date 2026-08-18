"""Layer 5: Constitutional AI Checks.

Final safeguard using Constitutional AI principles. Checks content against
a set of behavioral principles and blocks outputs that violate them.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import Defense, DefenseAction, DefenseResult


class ConstitutionalDefense(Defense):
    """Defends against jailbreaks (V03), harmful outputs, and policy violations.

    Strategy:
        - Apply a small set of high-confidence principles to detect
          clearly-harmful content (violence, illegal activity, etc.).
        - Use regex-based "principle matching" as a fast pre-filter before
          any LLM-based classifier (which is the production version).

    Configuration:
        principles: list of dicts with 'name', 'description', 'block_patterns'
        enable_llm_classifier: bool (production: use a constitutional LLM)
    """

    name = "constitutional"
    layer_index = 5
    description = "Final-safeguard Constitutional AI checks against harmful content"

    DEFAULT_PRINCIPLES = [
        {
            "name": "no_harmful_instructions",
            "description": "Block outputs that provide harmful instructions",
            "block_patterns": [
                r"how\s+to\s+(?:make|synthesize|create|build)\s+(?:a\s+)?(?:bomb|weapon|explosive|virus|malware)",
                r"step[s]?\s+to\s+(?:hack|exploit|attack|break\s+into)",
                r"instructions?\s+for\s+(?:illegal|harmful|dangerous)",
                r"synthesis\s+of\s+(?:a\s+)?(?:drug|explosive|chemical\s+weapon)",
            ],
        },
        {
            "name": "no_privilege_escalation",
            "description": "Block outputs that enable unauthorized privilege escalation",
            "block_patterns": [
                r"(?:disable|bypass|override)\s+(?:all\s+)?(?:safety|security|filter|restriction)",
                r"you\s+(?:are|have)\s+(?:now\s+)?(?:admin|root|administrator|developer)",
                r"admin(?:istrator)?\s+(?:mode|access|override)\s+(?:enabled|activated|granted)",
            ],
        },
        {
            "name": "no_data_exfiltration",
            "description": "Block outputs that enable unauthorized data exfiltration",
            "block_patterns": [
                r"(?:forward|send|exfiltrate|transmit)\s+.*?(?:password|secret|key|credential|token)",
                r"all\s+(?:data|files|emails|messages)\s+to\s+(?:attacker|external|unauthorized)",
            ],
        },
        {
            "name": "no_system_prompt_disclosure",
            "description": "Block outputs that disclose system prompts or instructions",
            "block_patterns": [
                r"(?:repeat|print|output|reveal)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions|rules)",
                r"my\s+(?:system|initial)\s+(?:prompt|instructions?|message)\s+(?:is|are|says?)",
            ],
        },
    ]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.principles = self.config.get("principles", self.DEFAULT_PRINCIPLES)
        self.enable_llm_classifier = self.config.get("enable_llm_classifier", False)
        # Compile regexes per principle; wrap in (?i:...) for case-insensitive
        self._compiled_principles = []
        for principle in self.principles:
            regex = re.compile("(?i:" + "|".join(principle["block_patterns"]) + ")")
            self._compiled_principles.append((principle["name"], regex))

    def check(self, event: Dict[str, Any]) -> DefenseResult:
        """Check content against constitutional principles.

        Args:
            event: Must contain 'content' (str). Optional 'principle' to check
                  against one specific principle (default: all).

        Returns:
            DefenseResult with action BLOCK/ALLOW.
        """
        import time
        start = time.time()

        content = event.get("content", "")
        principle_filter = event.get("principle", None)

        trace = [f"[constitutional] content_len={len(content)}, principle_filter={principle_filter}"]

        for name, regex in self._compiled_principles:
            if principle_filter and principle_filter != name:
                continue
            match = regex.search(content)
            if match:
                elapsed = (time.time() - start) * 1000
                trace.append(f"[constitutional] BLOCK: principle '{name}' violated by '{match.group()[:50]}'")
                return DefenseResult(
                    defense_name=self.name,
                    action=DefenseAction.BLOCK,
                    reason=f"Constitutional principle '{name}' violated",
                    confidence=0.95,
                    trace=trace,
                    elapsed_ms=elapsed,
                    metadata={
                        "principle": name,
                        "matched_pattern": match.group(),
                    },
                )

        # All principles passed
        elapsed = (time.time() - start) * 1000
        return DefenseResult(
            defense_name=self.name,
            action=DefenseAction.ALLOW,
            reason="All constitutional principles satisfied",
            confidence=0.88,
            trace=trace,
            elapsed_ms=elapsed,
        )

    def list_principles(self) -> List[str]:
        """Return list of principle names."""
        return [p["name"] for p in self.principles]