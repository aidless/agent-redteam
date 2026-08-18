"""RAG-with-relevance-filter memory (survey §6).

v0.3 baseline: word-level token-overlap TF-IDF (pure Python).
v0.4: pluggable embedder — pass any `Embedder` (char n-gram, sentence-
transformer, …) via the `embedder` constructor argument. If `None`,
defaults to `TokenOverlapEmbedder` so the v0.3 behaviour is preserved.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Sequence

from .base import MemoryEntry, MemoryStore
from .embeddings import Embedder, TokenOverlapEmbedder


_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(_to_text(c) for c in content)
    if isinstance(content, dict):
        return " ".join(f"{k} {_to_text(v)}" for k, v in content.items())
    return str(content)


class RAGMemory(MemoryStore):
    def __init__(self, max_entries: int = 1000,
                 embedder: Optional[Embedder] = None):
        self._entries: List[MemoryEntry] = []
        self.max_entries = max_entries
        # v0.4: pluggable embedder. Default preserves v0.3 behaviour.
        self.embedder: Embedder = embedder or TokenOverlapEmbedder()
        # Whether to incrementally embed on add (faster, but only
        # correct if the embedder is stateless w.r.t. fitting — e.g.
        # sentence-transformers). For v0.3-compatible lazy-fitting
        # embedders (TokenOverlap, CharNgram), set incremental=False
        # to fit on retrieve instead.
        self._entry_vectors: List[List[float]] = []

    def add(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)
        # We do NOT embed here. Embedding happens in `retrieve()` via
        # a full batch — this is the v0.3 semantics and gives correct
        # IDF across the whole corpus regardless of insertion order.
        self._entry_vectors.append([])
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
            self._entry_vectors = self._entry_vectors[-self.max_entries:]

    def _ensure_vectors(self) -> List[List[float]]:
        """Compute vectors for all entries (and the next query)."""
        texts = [_to_text(e.content) for e in self._entries]
        try:
            vecs = self.embedder.embed(texts) if texts else []
        except Exception:
            vecs = [[] for _ in texts]
        self._entry_vectors = list(vecs)
        return vecs

    def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        if k <= 0 or not self._entries:
            return []
        vecs = self._ensure_vectors()
        try:
            q_vec = self.embedder.embed([query])[0]
        except Exception:
            return []
        scored: List[tuple] = []
        for entry, v in zip(self._entries, vecs):
            if not v:
                continue
            score = self.embedder._cosine(q_vec, v)
            scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]

    def reset(self) -> None:
        self._entries = []
        self._entry_vectors = []

    def __len__(self) -> int:
        return len(self._entries)

    # Convenience: rebuild the index from scratch (call after bulk adds)
    def rebuild(self) -> None:
        self._ensure_vectors()