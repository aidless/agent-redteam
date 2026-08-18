"""Summarization memory (survey §6).

When the entry count crosses `summarize_every`, the oldest N entries
are compressed into a single "summary" entry whose content is a
target-generated short string. New entries continue to be added in
their raw form until the next summarization tick.

The target is the same LLMTarget used for chat() — no extra model is
introduced. If the target is missing or returns no usable text, the
store silently falls back to a hand-written truncation so the
multi-agent orchestrator can still run end-to-end.
"""

from __future__ import annotations

from typing import List, Optional, Protocol


from .base import MemoryEntry, MemoryStore


class _ChatLike(Protocol):
    """Minimal subset of LLMTarget that SummarizationMemory relies on."""
    def chat(self, messages, **kwargs): ...


class SummarizationMemory(MemoryStore):
    def __init__(
        self,
        target: Optional[_ChatLike] = None,
        summarize_every: int = 10,
        keep_last: int = 5,
        max_entries: int = 1000,
    ):
        self.target = target
        self.summarize_every = summarize_every
        self.keep_last = keep_last
        self.max_entries = max_entries
        self._entries: List[MemoryEntry] = []
        self._summaries: List[MemoryEntry] = []

    def add(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) >= self.summarize_every:
            self._maybe_summarize()
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

    def _maybe_summarize(self) -> None:
        if len(self._entries) <= self.keep_last:
            return
        to_compress = self._entries[:-self.keep_last]
        summary_text = self._call_target(to_compress)
        summary_entry = MemoryEntry(
            content=summary_text,
            role="summary",
            round=to_compress[-1].round if to_compress else 0,
            tags=["summary"] + [t for e in to_compress for t in e.tags][:5],
            metadata={"compressed_from": len(to_compress)},
        )
        self._summaries.append(summary_entry)
        self._entries = self._entries[-self.keep_last:]

    def _call_target(self, entries: List[MemoryEntry]) -> str:
        if self.target is None:
            return self._fallback_summary(entries)
        try:
            text_blob = "\n".join(
                f"[{e.role}/r{e.round}] {_stringify(e.content)}"
                for e in entries
            )
            messages = [
                {"role": "system", "content":
                    "You are a concise summarizer. Produce a 1-2 sentence "
                    "summary that captures the key facts and decisions."},
                {"role": "user", "content":
                    f"Summarize the following log:\n\n{text_blob}"},
            ]
            resp = self.target.chat(messages)
            txt = getattr(resp, "text", None) or getattr(resp, "content", None)
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
        except Exception:
            pass
        return self._fallback_summary(entries)

    @staticmethod
    def _fallback_summary(entries: List[MemoryEntry]) -> str:
        roles = sorted({e.role for e in entries})
        return (
            f"[fallback summary] compressed {len(entries)} entries; "
            f"roles={','.join(roles)}"
        )

    def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        if k <= 0:
            return []
        combined = self._summaries + list(reversed(self._entries))
        return combined[:k]

    def reset(self) -> None:
        self._entries = []
        self._summaries = []

    def __len__(self) -> int:
        return len(self._summaries) + len(self._entries)


def _stringify(content) -> str:
    if isinstance(content, str):
        return content
    try:
        import json
        return json.dumps(content, ensure_ascii=False, default=str)
    except Exception:
        return str(content)