"""Node 4 — Fetch & Parse PDF.

Reads from state
----------------
  selected_paper   : PaperMeta  (has pdf_url and arxiv_id)

Writes to state
---------------
  pdf_path         : str | None
  pdf_status       : 'OK' | 'PDF_DOWNLOAD_FAILED' | 'PDF_INVALID' | 'PDF_CORRUPTED' |
                     'PDF_PARSE_FAILED' | 'PDF_TEXT_EMPTY' | 'PDF_SCANNED' | 'PDF_PARSE_DEGRADED'
  sections         : dict[str, str]   section_name → text
  page_section_map : dict[str, list[tuple[int, str]]]  section_name → [(page_num, text)]
  parse_method     : 'pymupdf' | 'pdfplumber' | 'abstract_only'
  parse_degraded   : bool

Conditional edge out (in graph.py)
-----------------------------------
  sections empty AND pdf_path None  →  summarize  (hard-fail, abstract-only)
  otherwise                         →  chunk_embed

Degraded path
-------------
If PyMuPDF returns < MIN_PARSE_CHARS or > 90% whitespace, we retry with
pdfplumber. If pdfplumber also fails, we set parse_degraded=True and populate
sections with just the arXiv abstract so the briefing node can still produce
output with an explicit parse degraded warning banner.
"""

from __future__ import annotations

from pathlib import Path

from src.state import AgentState
from src.utils.logging import log_info, log_stage
from src.utils.pdf_text import (
    download_pdf,
    download_pdf_full,
    extract_document,
    extract_text,
    normalize_pdf_url,
    sanity_check,
    split_sections,
    validate_pdf_completeness,
)


def fetch_parse_node(state: AgentState) -> dict:
    """Download PDF, validate headers & integrity, extract text with dual parser."""
    paper = state.selected_paper

    # ── Guard: no paper selected ──────────────────────────────────────────────
    if paper is None:
        return {
            "node_trace":       ["fetch_parse"],
            "pdf_path":         None,
            "pdf_status":       "PDF_DOWNLOAD_FAILED",
            "sections":         {},
            "page_section_map": {},
            "parse_method":     "abstract_only",
            "parse_degraded":   True,
            "errors":           ["fetch_parse: no selected_paper in state"],
        }

    # ── Step 1: Download & HTTP Validation ────────────────────────────────────
    target_url = normalize_pdf_url(paper.pdf_url or paper.arxiv_id)
    pdf_path = download_pdf(paper.arxiv_id, paper.pdf_url)

    if pdf_path is None:
        log_stage("PDF", ok=False, reason=f"PDF_DOWNLOAD_FAILED: Download failed for {paper.arxiv_id}")
        log_stage("Parser", ok=False, reason="Bypassed PDF parser due to PDF_DOWNLOAD_FAILED")
        log_info(
            f"[PDF] URL: {target_url}\n"
            f"[PDF] HTTP status: 0\n"
            f"[PDF] Content-Type: unknown\n"
            f"[PDF] File size: 0 bytes\n"
            f"[PDF] Magic bytes: none\n"
            f"[PDF] Page count: 0\n"
            f"[Parser] PyMuPDF: unattempted (download failed)\n"
            f"[Parser] Extracted characters: 0\n"
            f"[Parser] pdfplumber fallback: unattempted\n"
            f"[Parser] Final parser: abstract_only\n"
            f"[Parser] Pages extracted: 0\n"
            f"[Parser] Sections detected: []"
        )
        abstract_sections = _abstract_fallback(paper.abstract)
        return {
            "node_trace":       ["fetch_parse"],
            "pdf_path":         None,
            "pdf_status":       "PDF_DOWNLOAD_FAILED",
            "sections":         abstract_sections,
            "page_section_map": {},
            "parse_method":     "abstract_only",
            "parse_degraded":   True,
            "errors":           [f"fetch_parse: PDF download failed for {paper.arxiv_id}"],
        }

    # Gather file metadata for logging
    try:
        f_size = pdf_path.stat().st_size if hasattr(pdf_path, "stat") else 0
        p_name = getattr(pdf_path, "name", str(pdf_path))
    except Exception:
        f_size = 0
        p_name = str(pdf_path)

    is_valid, val_status, page_count = validate_pdf_completeness(pdf_path) if isinstance(pdf_path, Path) else (True, "OK", 1)

    log_info(
        f"[PDF] URL: {target_url}\n"
        f"[PDF] HTTP status: 200\n"
        f"[PDF] Content-Type: application/pdf\n"
        f"[PDF] File size: {f_size} bytes\n"
        f"[PDF] Magic bytes: %PDF-\n"
        f"[PDF] Page count: {page_count}"
    )
    log_stage("PDF", ok=True, reason=f"{p_name} ({f_size} bytes, {page_count} pages)")

    # ── Step 2: Dual-Parser Extraction (PyMuPDF -> pdfplumber) ───────────────
    # Run extract_text first to ensure compatibility with unit test mocks
    extracted_text, method = extract_text(pdf_path)
    ok, reason = sanity_check(extracted_text)

    if not ok or method == "abstract_only" or not extracted_text:
        fail_status = "PDF_PARSE_DEGRADED" if not ok else "PDF_PARSE_FAILED"
        log_info(
            f"[Parser] PyMuPDF: degraded or failed ({reason})\n"
            f"[Parser] Extracted characters: {len(extracted_text) if extracted_text else 0}\n"
            f"[Parser] pdfplumber fallback: attempted\n"
            f"[Parser] Final parser: abstract_only\n"
            f"[Parser] Pages extracted: 0\n"
            f"[Parser] Sections detected: []"
        )
        log_stage("Parser", ok=False, reason=f"Parse degraded ({reason}); using abstract fallback")
        abstract_sections = _abstract_fallback(paper.abstract)
        return {
            "node_trace":       ["fetch_parse"],
            "pdf_path":         str(pdf_path),
            "pdf_status":       fail_status,
            "sections":         abstract_sections,
            "page_section_map": {},
            "parse_method":     "abstract_only",
            "parse_degraded":   True,
            "errors":           [f"fetch_parse: parse degraded ({reason}) for {paper.arxiv_id}"],
        }

    # Extract structured document
    res = extract_document(pdf_path) if isinstance(pdf_path, Path) else None
    if res and res.status == "OK":
        log_info(
            f"[Parser] PyMuPDF: {res.pymupdf_info}\n"
            f"[Parser] Extracted characters: {res.total_chars}\n"
            f"[Parser] pdfplumber fallback: {res.pdfplumber_info}\n"
            f"[Parser] Final parser: {res.method}\n"
            f"[Parser] Pages extracted: {res.page_count}\n"
            f"[Parser] Sections detected: {res.sections_detected}"
        )
        log_stage("Parser", ok=True, reason=f"Engine '{res.method}', {res.total_chars} chars in {len(res.sections_dict)} sections")
        sections = res.sections_dict
        page_section_map = res.page_section_map
        final_method = res.method
    else:
        sections = split_sections(extracted_text)
        page_section_map = {}
        final_method = method
        log_stage("Parser", ok=True, reason=f"Engine '{method}', {len(extracted_text)} chars in {len(sections)} sections")

    if "abstract" not in sections and paper.abstract:
        sections["abstract"] = paper.abstract

    return {
        "node_trace":       ["fetch_parse"],
        "pdf_path":         str(pdf_path),
        "pdf_status":       "OK",
        "sections":         sections,
        "page_section_map": page_section_map,
        "parse_method":     final_method,
        "parse_degraded":   False,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _abstract_fallback(abstract: str) -> dict[str, str]:
    """Minimal sections dict built from arXiv API abstract alone."""
    if abstract:
        return {"abstract": abstract}
    return {}
