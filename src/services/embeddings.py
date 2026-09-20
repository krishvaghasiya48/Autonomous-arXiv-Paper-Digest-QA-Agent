"""Embedding service — loads all-MiniLM-L6-v2 once as a module singleton.

Why all-MiniLM-L6-v2?
----------------------
- Runs locally on CPU, no API key.
- 384-dim vectors, fast inference (~500 sentences/sec on CPU).
- Strong semantic similarity for short-to-medium text (≤256 tokens ≈ ~900 chars).
- Direct match for the chunk size we chose.

Singleton pattern
-----------------
SentenceTransformer is expensive to initialise (~2s, ~90 MB).
We load it once at module level and reuse across all calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import EMBEDDING_MODEL

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _STType

_model: "_STType | None" = None


def _get_model():
    """Lazy-load the embedding model once and cache it."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings.  Returns list of float vectors.

    Uses batch encoding for efficiency.  Returns [] on empty input.
    """
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    """Embed a single query string.  Returns a float vector."""
    return embed_texts([text])[0]
