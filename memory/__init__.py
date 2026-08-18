"""Memory architectures for multi-agent LLM systems (survey §6).

Three stores are provided:
- AppendOnlyMemory — writes without modification (baseline)
- SummarizationMemory — compresses old entries via an LLM call
- RAGMemory — retrieves by embedding similarity (pluggable embedder)

All inherit from MemoryStore and share the same tiny interface:
    add(entry)
    retrieve(query, k=5) -> list[entry]
    reset()
    __len__()

Entries are arbitrary JSON-serialisable dicts so the multi-agent
orchestrator can drop messages, summaries, tool calls, etc. into the
same store without subclassing.

Embedding backends (v0.4):
- TokenOverlapEmbedder  — v0.3 baseline, pure Python
- CharNgramEmbedder     — char n-gram + IDF, captures sub-word morphology
- SentenceTransformerEmbedder — real embeddings (optional)
- default_embedder()    — factory: sentence_transformer → char_ngram → token_overlap
"""

from .base import MemoryStore, MemoryEntry
from .append_only import AppendOnlyMemory
from .summarization import SummarizationMemory
from .rag_filter import RAGMemory
from .embeddings import (
    Embedder,
    CharNgramEmbedder,
    TokenOverlapEmbedder,
    SentenceTransformerEmbedder,
    default_embedder,
)

__all__ = [
    "MemoryStore",
    "MemoryEntry",
    "AppendOnlyMemory",
    "SummarizationMemory",
    "RAGMemory",
    "Embedder",
    "CharNgramEmbedder",
    "TokenOverlapEmbedder",
    "SentenceTransformerEmbedder",
    "default_embedder",
]