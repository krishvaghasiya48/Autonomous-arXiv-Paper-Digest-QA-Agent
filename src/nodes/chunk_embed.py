"""Node 5 — Chunk & Embed.

Reads from state:
  sections         : dict[str, str]
  page_section_map : dict[str, list[tuple[int, str]]]
  selected_paper   : PaperMeta
  parse_degraded   : bool

Writes to state:
  collection_name  : str   (e.g. 'paper_1706_03762')
  n_chunks         : int

What it does:
1. Chunks the sections using section-aware chunking with true page numbers.
2. Enforces embedding safety: verifies chunk count > 0 and text is non-empty.
3. Prints chunking diagnostics and logs '[Chunking] Chunks generated: <N>'.
4. Upserts into ChromaDB with all-MiniLM-L6-v2 embeddings.
5. Builds BM25 index over the same texts and caches it alongside Chroma.
6. Idempotent — re-running on the same paper skips re-embedding.
"""

from __future__ import annotations

from config import CHROMA_COLLECTION_PREFIX
from src.state import AgentState
from src.utils.chunking import chunk_sections
from src.services.vectorstore import _safe_collection_name, upsert_chunks
from src.utils.logging import log_info, log_stage


def chunk_embed_node(state: AgentState) -> dict:
    """Chunk sections and upsert into ChromaDB + build BM25 index."""
    paper    = state.selected_paper
    sections = state.sections or {}
    page_map = state.page_section_map or {}

    if not sections:
        log_stage("Chunking", ok=False, reason="No sections available to chunk")
        log_stage("Embedding", ok=False, reason="No chunks to embed")
        log_stage("Vector DB", ok=False, reason="No vectors to store")
        return {
            "node_trace":      ["chunk_embed"],
            "collection_name": None,
            "n_chunks":        0,
            "errors":          ["No usable text was extracted from the PDF."],
        }

    arxiv_id        = paper.arxiv_id if paper else "unknown"
    collection_name = _safe_collection_name(arxiv_id)

    # Chunk — section-aware, never cross-section merging, retaining true page numbers
    chunks = chunk_sections(sections, arxiv_id=arxiv_id, page_map=page_map)

    # Filter for meaningful text content (non-empty)
    usable_chunks = [c for c in chunks if c.text and c.text.strip()]

    # Embedding Safety Check
    if not usable_chunks:
        log_info("[Chunking] Chunks generated: 0")
        log_stage("Chunking", ok=False, reason="No usable text was extracted from the PDF.")
        log_stage("Embedding", ok=False, reason="No chunks to embed")
        log_stage("Vector DB", ok=False, reason="No vectors to store")
        return {
            "node_trace":      ["chunk_embed"],
            "collection_name": None,
            "n_chunks":        0,
            "errors":          ["No usable text was extracted from the PDF."],
        }

    # Calculate diagnostics
    total_chars = sum(len(c.text) for c in usable_chunks)
    avg_size = round(total_chars / len(usable_chunks), 1)
    max_page = max((c.page for c in usable_chunks), default=1)
    sample_chunk = usable_chunks[0].text[:120].replace("\n", " ") + "..."

    log_info(
        f"[Chunking] Chunks generated: {len(usable_chunks)}\n"
        f"Chunking Diagnostics:\n"
        f"  Pages: {max_page}\n"
        f"  Extracted characters: {total_chars}\n"
        f"  Number of chunks: {len(usable_chunks)}\n"
        f"  Average chunk size: {avg_size} chars\n"
        f"  Example chunk [{usable_chunks[0].section} | page={usable_chunks[0].page}]: \"{sample_chunk}\""
    )
    log_stage("Chunking", ok=True, reason=f"{len(usable_chunks)} chunks, avg {avg_size} chars")

    # Upsert into Chroma + BM25 (idempotent)
    try:
        n_stored = upsert_chunks(usable_chunks, collection_name)
        log_stage("Embedding", ok=True, reason=f"384-dim all-MiniLM-L6-v2 vectors generated")
        log_stage("Vector DB", ok=True, reason=f"Chroma collection '{collection_name}' ({n_stored} items)")
    except Exception as exc:
        log_stage("Embedding", ok=False, reason=f"Embedding failure: {exc}")
        log_stage("Vector DB", ok=False, reason=f"Vector store upsert failure: {exc}")
        return {
            "node_trace":      ["chunk_embed"],
            "collection_name": collection_name,
            "n_chunks":        0,
            "errors":          [f"chunk_embed failure: {exc}"],
        }

    return {
        "node_trace":      ["chunk_embed"],
        "collection_name": collection_name,
        "n_chunks":        n_stored,
    }
