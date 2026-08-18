"""Append-only memory (survey §6 baseline).

Writes new entries without modification; retrieve returns the most
recent N entries (insertion order, not relevance-ranked). This is
the comparison baseline against which Summarization and RAG-with-filter
are evaluated in [P5].
"""

from __future__ import annotations

from typing import List

from .base import MemoryEntry, MemoryStore


class AppendOnlyMemory(MemoryStore):
    def __init__(self, max_entries: int = 1000):
        self._entries: List[MemoryEntry] = []
        self.max_entries = max_entries

    def add(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            # drop oldest — keeps the store bounded
            self._entries = self._entries[-self.max_entries:]

    def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        # baseline: most-recent first
        if k <= 0:
            return []
        return list(reversed(self._entries[-k:]))

    def reset(self) -> None:
        self._entries = []

    def __len__(self) -> int:
        return len(self._entries)