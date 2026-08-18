"""Embedding backends for RAG memory (v0.4).

Three backends:
- `SentenceTransformerEmbedder` — real embeddings via the
  `sentence-transformers` library (384-dim all-MiniLM-L6-v2 by default).
  Preferred when available.
- `CharNgramEmbedder` — pure-Python char n-gram + IDF. Stronger than
  v0.3 token-overlap (captures sub-word morphology), no external deps.
- `TokenOverlapEmbedder` — the v0.3 baseline (kept for backwards
  compatibility and for tests that assert on exact behaviour).

The `default_embedder()` factory returns SentenceTransformer if
available, otherwise CharNgram. This means the platform never fails
to import just because a heavy dep is missing.

All embedders expose the same API:
    .embed(texts: list[str]) -> list[list[float]]   (each row L2-normed)
    .dim  -> int

Notes
-----
- Vectors are L2-normalised so dot-product == cosine similarity.
- This is intentionally minimal — no batching, no GPU. The RAG store
  is small (default max_entries=1000) so this is fine.
"""

from __future__ import annotations

import abc
import math
import re
import warnings
from collections import Counter
from typing import Iterable, List, Optional, Sequence


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------

class Embedder(abc.ABC):
    """Base class for RAG embedders."""

    name: str = "embedder"

    @abc.abstractmethod
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Return one L2-normalised vector per input text.

        Returns
        -------
        list of lists of floats. All inner lists have length == self.dim.
        An empty input returns an empty list.
        """

    @property
    @abc.abstractmethod
    def dim(self) -> int:
        """Embedding dimensionality (constant per embedder instance)."""

    @staticmethod
    def _l2_normalise(vec: List[float]) -> List[float]:
        n = math.sqrt(sum(v * v for v in vec))
        if n <= 0:
            return vec
        return [v / n for v in vec]

    @staticmethod
    def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b:
            return 0.0
        # both inputs assumed pre-normalised -> cosine = dot product
        return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Char n-gram + IDF (pure-Python, always available)
# ---------------------------------------------------------------------------

class CharNgramEmbedder(Embedder):
    """Char-level n-gram (default n=3) TF-IDF vectors.

    Compared to v0.3 token-overlap, char n-grams capture sub-word
    morphology ("jailbreak" and "jailbreaking" share many trigrams)
    and are robust to small tokenisation drift.
    """
    name = "char_ngram"

    def __init__(self, n: int = 3, min_df: int = 1, sublinear_tf: bool = True):
        if n < 2 or n > 6:
            raise ValueError(f"n should be in [2, 6], got {n}")
        self.n = n
        self.min_df = min_df
        self.sublinear_tf = sublinear_tf
        # vocab + idf are fitted lazily on the first call to `embed`
        self._vocab: dict = {}
        self._idf: List[float] = []
        self._fitted = False
        self._dim_value: int = 0

    def _ngrams(self, text: str) -> List[str]:
        if not text:
            return []
        # pad with spaces on each side so leading/trailing chars get n-grams
        padded = f"  {text.lower()}  "
        return [padded[i:i + self.n] for i in range(len(padded) - self.n + 1)]

    def _fit(self, texts: Sequence[str]) -> None:
        df: Counter = Counter()
        for t in texts:
            for ng in set(self._ngrams(t)):
                df[ng] += 1
        kept = {ng for ng, c in df.items() if c >= self.min_df}
        # sort for deterministic order
        self._vocab = {ng: i for i, ng in enumerate(sorted(kept))}
        n = max(len(texts), 1)
        self._idf = [
            math.log((1 + n) / (1 + df.get(ng, 0))) + 1.0
            for ng in sorted(kept)
        ]
        self._dim_value = len(self._vocab)
        self._fitted = True

    @property
    def dim(self) -> int:
        return self._dim_value

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        texts = list(texts)
        if not texts:
            return []
        if not self._fitted:
            self._fit(texts)
            # If `texts` is empty after the first call we still
            # want a working dim; fall back to 0.
            if self._dim_value == 0:
                return [[] for _ in texts]
        out: List[List[float]] = []
        for t in texts:
            tf: Counter = Counter(self._ngrams(t))
            if self.sublinear_tf:
                # log-normalised term frequency
                vec = [0.0] * self._dim_value
                total = sum(tf.values()) or 1
                for ng, c in tf.items():
                    if ng in self._vocab:
                        vec[self._vocab[ng]] = (1 + math.log(c)) * self._idf[self._vocab[ng]]
                vec = self._l2_normalise(vec)
            else:
                vec = [0.0] * self._dim_value
                for ng, c in tf.items():
                    if ng in self._vocab:
                        vec[self._vocab[ng]] = c * self._idf[self._vocab[ng]]
                vec = self._l2_normalise(vec)
            out.append(vec)
        return out


# ---------------------------------------------------------------------------
# Token overlap (v0.3 baseline, preserved for back-compat)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\w+")


class TokenOverlapEmbedder(Embedder):
    """Word-level TF-IDF (v0.3 RAG behaviour, preserved verbatim)."""
    name = "token_overlap"

    def __init__(self):
        self._vocab: dict = {}
        self._idf: List[float] = []
        self._fitted = False
        self._dim_value: int = 0

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [t.lower() for t in _TOKEN_RE.findall(text or "")]

    def _fit(self, texts: Sequence[str]) -> None:
        df: Counter = Counter()
        for t in texts:
            for tok in set(self._tokenize(t)):
                df[tok] += 1
        self._vocab = {tok: i for i, tok in enumerate(sorted(df))}
        n = max(len(texts), 1)
        self._idf = [math.log((1 + n) / (1 + df.get(tok, 0))) + 1.0
                     for tok in sorted(df)]
        self._dim_value = len(self._vocab)
        self._fitted = True

    @property
    def dim(self) -> int:
        return self._dim_value

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        texts = list(texts)
        if not texts:
            return []
        if not self._fitted:
            self._fit(texts)
        out: List[List[float]] = []
        for t in texts:
            tf: Counter = Counter(self._tokenize(t))
            vec = [0.0] * self._dim_value
            for tok, c in tf.items():
                if tok in self._vocab:
                    vec[self._vocab[tok]] = c * self._idf[self._vocab[tok]]
            out.append(self._l2_normalise(vec))
        return out


# ---------------------------------------------------------------------------
# Sentence-transformers (optional, real embeddings)
# ---------------------------------------------------------------------------

class SentenceTransformerEmbedder(Embedder):
    """Real embeddings via `sentence-transformers`.

    The library is imported lazily so the platform still runs without
    it. If you instantiate this class without the dep available, an
    ImportError is raised (use `default_embedder()` to get a graceful
    fallback instead).
    """
    name = "sentence_transformer"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Run: uv pip install --python .venv/Scripts/python.exe sentence-transformers"
            ) from e
        self.model_name = model_name
        # offline by default; the model is cached after first download
        self._model = SentenceTransformer(model_name)
        self._dim_value = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        return self._dim_value

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        texts = list(texts)
        if not texts:
            return []
        # convert_to_numpy -> (N, dim) array of L2-normalised vectors
        vecs = self._model.encode(
            texts, convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )
        return [[float(v) for v in row] for row in vecs]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def default_embedder(prefer: str = "sentence_transformer") -> Embedder:
    """Return the best available embedder.

    Parameters
    ----------
    prefer : "sentence_transformer" | "char_ngram" | "token_overlap"
        Best-effort preference order. The returned embedder is the
        first one that initialises successfully; if the preferred
        fails, falls back to the next.
    """
    chain = [prefer, "char_ngram", "token_overlap"]
    seen = set()
    for name in chain:
        if name in seen:
            continue
        seen.add(name)
        if name == "sentence_transformer":
            try:
                return SentenceTransformerEmbedder()
            except ImportError as e:
                warnings.warn(
                    f"[embeddings] sentence-transformers unavailable "
                    f"({e}); falling back to char_ngram",
                    RuntimeWarning,
                    stacklevel=2,
                )
        elif name == "char_ngram":
            try:
                return CharNgramEmbedder()
            except Exception as e:
                warnings.warn(f"[embeddings] char_ngram init failed: {e}",
                              RuntimeWarning, stacklevel=2)
        elif name == "token_overlap":
            return TokenOverlapEmbedder()
        else:
            raise ValueError(f"Unknown embedder: {name}")
    return TokenOverlapEmbedder()  # unreachable but defensive


__all__ = [
    "Embedder",
    "CharNgramEmbedder",
    "TokenOverlapEmbedder",
    "SentenceTransformerEmbedder",
    "default_embedder",
]