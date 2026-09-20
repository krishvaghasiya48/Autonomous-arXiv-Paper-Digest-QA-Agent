"""Vector store service — ChromaDB (dense) + rank-bm25 (sparse) hybrid retrieval.

Design
------
One Chroma collection per paper, named  paper_<arxiv_id>
(safe chars only — slashes replaced with underscores).

Dense retrieval   : ChromaDB cosine similarity with all-MiniLM-L6-v2 embeddings.
Sparse retrieval  : BM25 index built over the same chunk texts, cached in memory.
Hybrid merge      : dense top-K + BM25 top-K → dedup by chunk_id → rerank by
                    reciprocal rank fusion → keep TOP_K_FINAL results.

Idempotent upsert
-----------------
If the collection already contains n_chunks matching what we'd insert, skip
re-embedding.  This means re-running `digest` on the same paper is fast.

Why hybrid?
-----------
Dense embeddings miss exact-term matches (model names, arXiv IDs, numbers).
BM25 catches those.  The combination costs almost nothing to add and improves
grounding on precise technical questions — exactly the kind the spec tests.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from config import (
    CHROMA_DIR,
    CHROMA_COLLECTION_PREFIX,
    TOP_K_BM25,
    TOP_K_DENSE,
    TOP_K_FINAL,
)
from src.services.embeddings import embed_query, embed_texts
from src.utils.chunking import Chunk

# BM25 index files cached alongside Chroma data
_BM25_CACHE_DIR = CHROMA_DIR / "bm25_indices"
_BM25_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_collection_name(arxiv_id: str) -> str:
    safe = arxiv_id.replace("/", "_").replace(":", "_").replace(".", "_")
    name = f"{CHROMA_COLLECTION_PREFIX}{safe}"
    return name[:60]


def _get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _get_collection(collection_name: str) -> Collection:
    client = _get_client()
    return client.get_or_create_collection(
        name     = collection_name,
        metadata = {"hnsw:space": "cosine"},
    )


# ── BM25 helpers ──────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _bm25_cache_path(collection_name: str) -> Path:
    return _BM25_CACHE_DIR / f"{collection_name}.pkl"


def _save_bm25(collection_name: str, texts: list[str], ids: list[str]) -> None:
    """Persist a BM25 index to disk alongside the Chroma data."""
    try:
        from rank_bm25 import BM25Okapi
        corpus  = [_tokenize(t) for t in texts]
        bm25    = BM25Okapi(corpus)
        payload = {"bm25": bm25, "ids": ids, "texts": texts}
        _bm25_cache_path(collection_name).write_bytes(pickle.dumps(payload))
    except Exception:
        pass  # BM25 is optional — dense-only fallback is acceptable


def _load_bm25(collection_name: str) -> tuple | None:
    """Load cached BM25 index.  Returns (bm25, ids, texts) or None."""
    path = _bm25_cache_path(collection_name)
    if not path.exists():
        return None
    try:
        payload = pickle.loads(path.read_bytes())
        return payload["bm25"], payload["ids"], payload["texts"]
    except Exception:
        return None


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def _rrf(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    """Merge multiple ranked ID lists using Reciprocal Rank Fusion.

    Higher score = better.  Returns IDs sorted best-first.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


# ── Public API ────────────────────────────────────────────────────────────────

def upsert_chunks(chunks: list[Chunk], collection_name: str) -> int:
    """Embed and upsert chunks into Chroma.  Returns number of chunks stored.

    Idempotent: if the collection already has the same number of chunks,
    we skip re-embedding (fast re-run).
    """
    if not chunks:
        return 0

    collection = _get_collection(collection_name)

    # Idempotency check
    existing = collection.count()
    if existing == len(chunks):
        return existing

    texts     = [c.text for c in chunks]
    ids       = [c.chunk_id for c in chunks]
    metadatas = [c.to_metadata() for c in chunks]
    embeddings = embed_texts(texts)

    collection.upsert(
        ids        = ids,
        documents  = texts,
        embeddings = embeddings,
        metadatas  = metadatas,
    )

    # Build and cache BM25 index over the same texts
    _save_bm25(collection_name, texts, ids)

    return collection.count()


def query_hybrid(
    question: str,
    collection_name: str,
    n_results: int = TOP_K_FINAL,
) -> list[dict]:
    """Hybrid dense + BM25 retrieval.

    Returns up to n_results dicts, each with keys:
      chunk_id, text, metadata, score
    """
    collection = _get_collection(collection_name)
    total = collection.count()
    if total == 0:
        return []

    # ── Dense retrieval ───────────────────────────────────────────────────────
    dense_k   = min(TOP_K_DENSE, total)
    q_vec     = embed_query(question)
    dense_raw = collection.query(
        query_embeddings = [q_vec],
        n_results        = dense_k,
        include          = ["documents", "metadatas", "distances"],
    )
    dense_ids  = (dense_raw.get("ids") or [[]])[0]
    dense_docs = (dense_raw.get("documents") or [[]])[0]
    dense_meta = (dense_raw.get("metadatas") or [[]])[0]
    dense_dist = (dense_raw.get("distances") or [[]])[0]

    # Build lookup: chunk_id → {text, metadata, distance}
    lookup: dict[str, dict] = {}
    for cid, doc, meta, dist in zip(dense_ids, dense_docs, dense_meta, dense_dist):
        lookup[cid] = {"text": doc, "metadata": meta or {}, "distance": dist}

    # ── BM25 retrieval ────────────────────────────────────────────────────────
    bm25_ids: list[str] = []
    bm25_data = _load_bm25(collection_name)
    if bm25_data is not None:
        bm25_obj, all_ids, all_texts = bm25_data
        bm25_k     = min(TOP_K_BM25, len(all_ids))
        q_tokens   = _tokenize(question)
        scores     = bm25_obj.get_scores(q_tokens)
        top_idx    = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:bm25_k]
        bm25_ids   = [all_ids[i] for i in top_idx]

        # Add BM25 results to lookup if not already present
        for cid in bm25_ids:
            if cid not in lookup:
                # Fetch from Chroma by ID
                try:
                    fetched = collection.get(ids=[cid], include=["documents", "metadatas"])
                    if fetched["ids"]:
                        lookup[cid] = {
                            "text":     fetched["documents"][0],
                            "metadata": fetched["metadatas"][0] or {},
                            "distance": 1.0,   # unknown distance for BM25-only hits
                        }
                except Exception:
                    pass

    # ── Merge with RRF ────────────────────────────────────────────────────────
    merged = _rrf([dense_ids, bm25_ids])[:n_results]

    results = []
    for rank, cid in enumerate(merged):
        if cid not in lookup:
            continue
        entry = lookup[cid]
        results.append({
            "chunk_id": cid,
            "text":     entry["text"],
            "metadata": entry["metadata"],
            "score":    round(1.0 - entry.get("distance", 0.5), 4),
            "rank":     rank + 1,
        })

    from src.utils.logging import log_info
    log_info(f"Hybrid Retrieval Diagnostics: Dense results: {len(dense_ids)} | BM25 results: {len(bm25_ids)} | Combined results: {len(results)}")

    return results


def collection_exists(collection_name: str) -> bool:
    """Return True if the collection has at least one chunk."""
    try:
        col = _get_collection(collection_name)
        return col.count() > 0
    except Exception:
        return False
