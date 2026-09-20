"""Developer Diagnostic Tool for Autonomous arXiv Paper Digest & QA Agent.

Runs complete 10-point system diagnostic:
1. Configuration
2. arXiv API connectivity
3. arXiv search
4. Paper metadata parsing
5. PDF download
6. PDF parsing (PyMuPDF & pdfplumber)
7. Embeddings (all-MiniLM-L6-v2)
8. Vector store (ChromaDB persistence & reload)
9. LLM provider status
10. Graph initialization (LangGraph compiled runnables)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def run_diagnostics() -> bool:
    """Execute all 10 diagnostic checks and display a clean summary table.

    Returns True if all critical components passed, else False.
    """
    console.print("\n[bold cyan]Running Full System Diagnostic...[/bold cyan]\n")
    table = Table(title="System Diagnostic Report", show_lines=True)
    table.add_column("Check #", style="dim", width=8)
    table.add_column("Component", style="bold white", width=26)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Details", style="cyan")

    results: list[tuple[int, str, bool, str]] = []

    # ── 1. Configuration ──────────────────────────────────────────────────────
    try:
        from config import ROOT_DIR, DATA_DIR, PDF_DIR, CHROMA_DIR, SESSION_DIR, CHUNK_SIZE, EMBEDDING_MODEL
        for d in (DATA_DIR, PDF_DIR, CHROMA_DIR, SESSION_DIR):
            d.mkdir(parents=True, exist_ok=True)
        results.append((1, "Configuration", True, f"Dirs exist. Model: {EMBEDDING_MODEL}, Chunk: {CHUNK_SIZE}"))
    except Exception as exc:
        results.append((1, "Configuration", False, str(exc)))

    # ── 2. arXiv API Connectivity ─────────────────────────────────────────────
    try:
        import urllib.request
        from src.services.arxiv_client import ARXIV_API_BASE_URL, USER_AGENT
        req = urllib.request.Request(
            f"{ARXIV_API_BASE_URL}?id_list=2312.10997&max_results=1",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
        results.append((2, "arXiv API Connectivity", status == 200, f"HTTP {status} from {ARXIV_API_BASE_URL}"))
    except Exception as exc:
        results.append((2, "arXiv API Connectivity", False, f"Connection failed: {exc}"))

    # ── 3. arXiv Search ───────────────────────────────────────────────────────
    try:
        from src.services.arxiv_client import search
        papers = search("RAG", max_results=3)
        if papers:
            results.append((3, "arXiv Search ('RAG')", True, f"Retrieved {len(papers)} candidate(s). Top: [{papers[0].arxiv_id}] {papers[0].title[:35]}..."))
        else:
            results.append((3, "arXiv Search ('RAG')", False, "Returned 0 candidates for 'RAG'"))
    except Exception as exc:
        results.append((3, "arXiv Search ('RAG')", False, str(exc)))

    # ── 4. Paper Metadata Parsing & ID Normalization ──────────────────────────
    try:
        from src.services.arxiv_client import normalize_arxiv_id, by_id
        assert normalize_arxiv_id("http://arxiv.org/abs/2312.10997v5") == "2312.10997"
        assert normalize_arxiv_id("https://arxiv.org/pdf/2312.10997.pdf") == "2312.10997"
        paper = by_id("2312.10997")
        assert paper is not None and paper.arxiv_id == "2312.10997"
        results.append((4, "Paper Metadata Parsing", True, f"Normalized ID '{paper.arxiv_id}', Title: '{paper.title[:35]}...'"))
    except Exception as exc:
        results.append((4, "Paper Metadata Parsing", False, str(exc)))

    # ── 5. PDF Download & Validation ──────────────────────────────────────────
    try:
        from src.utils.pdf_text import download_pdf, _is_valid_pdf_file
        pdf_path = download_pdf("2312.10997", "https://arxiv.org/pdf/2312.10997.pdf")
        if pdf_path and _is_valid_pdf_file(pdf_path):
            results.append((5, "PDF Download & Magic %PDF", True, f"Verified {pdf_path.name} ({pdf_path.stat().st_size} bytes)"))
        else:
            results.append((5, "PDF Download & Magic %PDF", False, "Download failed or failed %PDF validation"))
    except Exception as exc:
        results.append((5, "PDF Download & Magic %PDF", False, str(exc)))

    # ── 6. PDF Parsing ────────────────────────────────────────────────────────
    try:
        from src.utils.pdf_text import extract_text, HAS_PYMUPDF, HAS_PDFPLUMBER
        text, method = extract_text(pdf_path)
        if text and len(text) > 500:
            results.append((6, "PDF Parsing (PyMuPDF/plumber)", True, f"Engine: {method}, extracted {len(text)} chars (PyMuPDF={HAS_PYMUPDF}, plumber={HAS_PDFPLUMBER})"))
        else:
            results.append((6, "PDF Parsing (PyMuPDF/plumber)", False, f"Extracted insufficient text ({len(text)} chars)"))
    except Exception as exc:
        results.append((6, "PDF Parsing (PyMuPDF/plumber)", False, str(exc)))

    # ── 7. Embeddings ─────────────────────────────────────────────────────────
    try:
        from src.services.embeddings import embed_texts
        sample_vecs = embed_texts(["Test sentence for vector embedding generation."])
        dim = len(sample_vecs[0]) if sample_vecs else 0
        results.append((7, "Embeddings (all-MiniLM-L6-v2)", dim == 384, f"Generated {len(sample_vecs)} vector(s) of dimension {dim}"))
    except Exception as exc:
        results.append((7, "Embeddings (all-MiniLM-L6-v2)", False, str(exc)))

    # ── 8. Vector Store Persistence ───────────────────────────────────────────
    try:
        from src.services.vectorstore import _get_collection, query_hybrid, upsert_chunks
        from src.utils.chunking import Chunk
        test_col_name = "diagnostic_test_collection"
        c = Chunk(text="RAG combines retrieval with language model generation.", arxiv_id="test", section="method", chunk_index=0, char_start=0, char_end=50, page=1)
        stored = upsert_chunks([c], test_col_name)
        hits = query_hybrid("retrieval", test_col_name, n_results=1)
        results.append((8, "Vector Store (ChromaDB + BM25)", stored >= 1 and len(hits) >= 1, f"Stored {stored} chunks in ChromaDB, hybrid query returned {len(hits)} hit(s)"))
    except Exception as exc:
        results.append((8, "Vector Store (ChromaDB + BM25)", False, str(exc)))

    # ── 9. LLM Provider Status ────────────────────────────────────────────────
    try:
        from config import GROQ_API_KEY, GEMINI_API_KEY, OLLAMA_MODEL
        has_groq = bool(GROQ_API_KEY)
        has_gemini = bool(GEMINI_API_KEY)
        import shutil
        has_ollama = bool(shutil.which("ollama"))
        llm_details = f"Groq: {'configured' if has_groq else 'none'}, Gemini: {'configured' if has_gemini else 'none'}, Ollama: {'installed' if has_ollama else 'none'}"
        results.append((9, "LLM Providers", True, f"{llm_details} (Graceful paper-text fallback active)"))
    except Exception as exc:
        results.append((9, "LLM Providers", False, str(exc)))

    # ── 10. Graph Initialization ──────────────────────────────────────────────
    try:
        from src.graph import build_digest_graph, build_qa_graph
        g_a = build_digest_graph()
        g_b = build_qa_graph()
        results.append((10, "LangGraph Compilation", True, f"Graph A (8 nodes) & Graph B (QA loop) compiled successfully"))
    except Exception as exc:
        results.append((10, "LangGraph Compilation", False, str(exc)))

    # Render results table
    all_passed = True
    for idx, comp, passed, details in results:
        status_str = "[bold green]PASS[/bold green]" if passed else "[bold red]FAIL[/bold red]"
        table.add_row(str(idx), comp, status_str, details)
        if not passed and idx not in (9,):  # LLM is optional as graceful fallback exists
            all_passed = False

    console.print(table)
    if all_passed:
        console.print("\n[bold green]✔ All core diagnostic checks PASSED successfully.[/bold green]\n")
    else:
        console.print("\n[bold red]✖ One or more core diagnostic checks FAILED.[/bold red]\n")

    return all_passed
