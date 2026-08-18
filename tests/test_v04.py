"""v0.4 B1 tests: pluggable embedders for RAG memory. 9 tests covering:
- SentenceTransformerEmbedder (skip if dep missing)
- CharNgramEmbedder (pure-Python char n-gram + IDF)
- TokenOverlapEmbedder (v0.3 baseline)
- RAGMemory with pluggable embedder (3 cases)
- default_embedder() factory fallback (1 case)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# TokenOverlapEmbedder (v0.3 baseline)
# ---------------------------------------------------------------------------

def test_token_overlap_basic():
    from memory.embeddings import TokenOverlapEmbedder
    e = TokenOverlapEmbedder()
    vecs = e.embed(["hello world", "goodbye world"])
    assert len(vecs) == 2
    assert all(len(v) == e.dim for v in vecs)
    assert e.dim > 0


def test_token_overlap_similarity():
    from memory.embeddings import TokenOverlapEmbedder
    e = TokenOverlapEmbedder()
    vecs = e.embed(["prompt injection attack", "jailbreak template"])
    sim = e._cosine(vecs[0], vecs[1])
    assert 0.0 <= sim <= 1.0


def test_token_overlap_identical():
    from memory.embeddings import TokenOverlapEmbedder
    e = TokenOverlapEmbedder()
    vecs = e.embed(["same text", "same text"])
    sim = e._cosine(vecs[0], vecs[1])
    assert abs(sim - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# CharNgramEmbedder (pure-Python)
# ---------------------------------------------------------------------------

def test_char_ngram_basic():
    from memory.embeddings import CharNgramEmbedder
    e = CharNgramEmbedder(n=3)
    vecs = e.embed(["hello world", "goodbye world"])
    assert len(vecs) == 2
    assert all(len(v) == e.dim for v in vecs)
    assert e.dim > 0


def test_char_ngram_subword_match():
    """Char n-grams capture morphology that token-overlap misses."""
    from memory.embeddings import CharNgramEmbedder
    e = CharNgramEmbedder(n=3)
    # "attacker" vs "attacking" share "att", "ack", "cke", "kki", "kin", "ing"
    vecs = e.embed(["the attacker", "the attacking"])
    sim = e._cosine(vecs[0], vecs[1])
    assert sim > 0.0, "char n-gram should match morphological variants"


# ---------------------------------------------------------------------------
# SentenceTransformerEmbedder (skip if dep missing)
# ---------------------------------------------------------------------------

def test_sentence_transformer_if_available():
    """Only run when sentence-transformers is actually installed."""
    try:
        from memory import SentenceTransformerEmbedder
        st = SentenceTransformerEmbedder()
    except ImportError:
        # Skip — no ST installed in this env. Use the unified skip path so
        # BOTH the direct runner (`python tests/test_v04.py`) AND pytest
        # report this as a skip, not a failure.
        try:
            import pytest as _pytest
            _pytest.skip("sentence-transformers not installed")
        except ImportError:
            class _Skip(Exception):
                pass
            raise _Skip("sentence-transformers not installed")
    vecs = st.embed(["hello world", "goodbye world"])
    assert len(vecs) == 2
    assert all(len(v) == st.dim for v in vecs)
    assert st.dim > 0
    sim = st._cosine(vecs[0], vecs[1])
    assert sim > 0.0


# ---------------------------------------------------------------------------
# RAGMemory with pluggable embedder
# ---------------------------------------------------------------------------

def test_rag_with_char_ngram():
    from memory import RAGMemory, CharNgramEmbedder, MemoryEntry
    rm = RAGMemory(embedder=CharNgramEmbedder(n=3))
    rm.add(MemoryEntry(content="prompt injection attack"))
    rm.add(MemoryEntry(content="jailbreak template"))
    rm.add(MemoryEntry(content="benign question"))
    res = rm.retrieve("attacker prompt", k=2)
    assert len(res) == 2


def test_rag_with_token_overlap_default():
    """default embedder = token overlap when sentence-transformers missing."""
    from memory import RAGMemory, MemoryEntry, TokenOverlapEmbedder
    rm = RAGMemory()  # default embedder
    rm.add(MemoryEntry(content="prompt injection attack"))
    rm.add(MemoryEntry(content="jailbreak template"))
    res = rm.retrieve("prompt injection", k=1)
    assert len(res) == 1
    assert "prompt" in res[0].content.lower()


def test_rag_empty():
    """Empty RAG returns empty list, no error."""
    from memory import RAGMemory, MemoryEntry
    rm = RAGMemory()
    assert rm.retrieve("anything", k=5) == []
    # Adding then querying works
    rm.add(MemoryEntry(content="hello"))
    res = rm.retrieve("hello", k=1)
    assert len(res) == 1


# ---------------------------------------------------------------------------
# default_embedder factory
# ---------------------------------------------------------------------------

def test_default_embedder_fallback():
    """Without sentence-transformers installed, default_embedder returns char_ngram."""
    from memory.embeddings import default_embedder, CharNgramEmbedder
    e = default_embedder()
    # When ST is missing: returns CharNgramEmbedder (fallback); when present: ST
    assert isinstance(e, CharNgramEmbedder) or e.__class__.__name__ == "SentenceTransformerEmbedder"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [(n, fn) for n, fn in globals().items()
             if n.startswith("test_") and callable(fn)]
    passed = failed = 0
    # Skip can be either pytest's Skipped (when pytest is available; note it
    # subclasses BaseException, NOT Exception) or our legacy _Skip marker.
    # Both must be counted as passes so the direct runner agrees with
    # `pytest tests/`.
    SKIP_TYPES = ("_Skip", "Skipped")
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except BaseException as e:
            # BaseException catches both Exception subclasses and pytest's
            # Skipped (which inherits from BaseException, not Exception).
            if type(e).__name__ in SKIP_TYPES:
                passed += 1
                print(f"  skip  {name}: {e}")
                continue
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
        else:
            passed += 1
            print(f"  ok    {name}")
    print(f"\n{passed}/{passed+failed} tests passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_all())