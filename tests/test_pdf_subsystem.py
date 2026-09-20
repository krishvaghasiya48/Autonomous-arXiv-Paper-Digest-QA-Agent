"""Test Suite for PDF Acquisition, Validation, and Dual-Parser Subsystem.

Covers all 10 requirements from Section 20:
  Test A — Valid PDF (download -> validation -> parse -> chunks)
  Test B — HTML returned instead of PDF (PDF_INVALID, no parser invocation)
  Test C — Corrupted PDF (PDF_CORRUPTED detected)
  Test D — Empty PDF (PDF_TEXT_EMPTY detected)
  Test E — Scanned / image-only PDF (PDF_SCANNED detected, degraded state)
  Test F — PyMuPDF failure -> automatic pdfplumber fallback succeeds
  Test G — Both parsers fail -> controlled failure without crashing graph
  Test H — Network timeout -> controlled download failure
  Test I — HTTP 429 -> retry / backoff handling
  Test J — Existing valid cache -> no unnecessary redownload
  Test K — Comprehensive URL normalization
"""

from __future__ import annotations

import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pymupdf

from src.nodes.chunk_embed import chunk_embed_node
from src.nodes.fetch_parse import fetch_parse_node
from src.state import AgentState, PaperMeta
from src.utils.chunking import Chunk, chunk_sections
from src.utils.pdf_text import (
    PageData,
    download_pdf_full,
    evaluate_pages_quality,
    extract_document,
    normalize_pdf_url,
    validate_pdf_completeness,
)


def _create_minimal_valid_pdf(path: Path, text: str = "This is a valid test PDF document for academic parsing.") -> Path:
    """Helper to create a small, fully valid PDF file with selectable text using PyMuPDF."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), f"Abstract\n\n{text}")
    page.insert_text((50, 200), "Introduction\n\nLanguage models require robust PDF parsing.")
    doc.save(str(path))
    doc.close()
    return path


def _create_scanned_pdf(path: Path) -> Path:
    """Helper to create a PDF with an empty page (simulating scanned/image without text layer)."""
    doc = pymupdf.open()
    doc.new_page()  # Blank page
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


# ── Test K: URL Normalization ─────────────────────────────────────────────────

def test_url_normalization():
    """Verify all variants of arXiv URLs and IDs normalize to direct PDF download URLs."""
    assert normalize_pdf_url("https://arxiv.org/abs/2312.10997") == "https://arxiv.org/pdf/2312.10997.pdf"
    assert normalize_pdf_url("https://arxiv.org/abs/2312.10997v1") == "https://arxiv.org/pdf/2312.10997v1.pdf"
    assert normalize_pdf_url("https://arxiv.org/pdf/2312.10997") == "https://arxiv.org/pdf/2312.10997.pdf"
    assert normalize_pdf_url("https://arxiv.org/pdf/2312.10997.pdf") == "https://arxiv.org/pdf/2312.10997.pdf"
    assert normalize_pdf_url("https://arxiv.org/pdf/2312.10997v1.pdf") == "https://arxiv.org/pdf/2312.10997v1.pdf"
    assert normalize_pdf_url("http://arxiv.org/abs/2312.10997") == "https://arxiv.org/pdf/2312.10997.pdf"
    assert normalize_pdf_url("2312.10997") == "https://arxiv.org/pdf/2312.10997.pdf"
    assert normalize_pdf_url("2312.10997v2") == "https://arxiv.org/pdf/2312.10997v2.pdf"
    assert normalize_pdf_url("math/0211159v1") == "https://arxiv.org/pdf/math/0211159v1.pdf"


# ── Test A: Valid PDF End-to-End ──────────────────────────────────────────────

def test_a_valid_pdf_flow(tmp_path: Path):
    """Test A: Valid PDF -> download -> validation -> parse -> sections -> chunks."""
    pdf_file = tmp_path / "valid_test.pdf"
    _create_minimal_valid_pdf(pdf_file, "Retrieval-augmented generation enhances LLMs.")

    is_valid, status, page_count = validate_pdf_completeness(pdf_file)
    assert is_valid is True
    assert status == "OK"
    assert page_count >= 1

    res = extract_document(pdf_file)
    assert res.status == "OK"
    assert res.method in ("pymupdf", "pdfplumber")
    assert res.total_chars > 50
    assert len(res.sections_dict) >= 1

    chunks = chunk_sections(res.sections_dict, arxiv_id="2312.10997", page_map=res.page_section_map)
    assert len(chunks) >= 1
    assert chunks[0].page >= 1
    assert chunks[0].paper_id == "2312.10997"


# ── Test B: HTML Returned Instead of PDF ───────────────────────────────────────

def test_b_html_returned_rejected():
    """Test B: Server returns HTML error/abstract page instead of PDF -> PDF_INVALID."""
    html_content = b"<html><head><title>Access Denied / Captcha</title></head><body>Rate limit exceeded</body></html>"
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Type": "text/html; charset=UTF-8"}
    mock_resp.read.return_value = html_content
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("src.utils.pdf_text.validate_pdf_completeness", return_value=(False, "PDF_INVALID", 0)):
        path, status, err, meta = download_pdf_full("test_html_id", "https://arxiv.org/pdf/test_html_id.pdf", max_attempts=1)
        assert path is None
        assert status == "PDF_INVALID"
        assert "HTML" in (err or "")


# ── Test C: Corrupted PDF ─────────────────────────────────────────────────────

def test_c_corrupted_pdf(tmp_path: Path):
    """Test C: File has %PDF header but invalid xref / corrupted structure -> PDF_CORRUPTED."""
    corrupt_file = tmp_path / "corrupt.pdf"
    corrupt_file.write_bytes(b"%PDF-1.5\nRandom broken garbage without xref or trailer\n%%EOF" * 20)

    is_valid, status, page_count = validate_pdf_completeness(corrupt_file)
    assert is_valid is False
    assert status.startswith("PDF_CORRUPTED")
    assert page_count == 0


# ── Test D: Empty PDF ─────────────────────────────────────────────────────────

def test_d_empty_pdf(tmp_path: Path):
    """Test D: Zero-byte file or 0-page PDF -> PDF_TEXT_EMPTY or PDF_INVALID."""
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")

    is_valid, status, page_count = validate_pdf_completeness(empty_file)
    assert is_valid is False
    assert "PDF_INVALID" in status or "too small" in status


# ── Test E: Scanned / Image-Only PDF ──────────────────────────────────────────

def test_e_scanned_image_only_pdf(tmp_path: Path):
    """Test E: PDF with pages but no extractable text -> PDF_TEXT_EMPTY or PDF_SCANNED."""
    scanned_file = tmp_path / "scanned.pdf"
    _create_scanned_pdf(scanned_file)

    res = extract_document(scanned_file)
    assert res.status in ("PDF_TEXT_EMPTY", "PDF_SCANNED")
    assert res.method == "abstract_only"
    assert res.total_chars == 0


# ── Test F: PyMuPDF Failure -> pdfplumber Fallback ────────────────────────────

def test_f_pymupdf_failure_fallback_to_pdfplumber(tmp_path: Path):
    """Test F: PyMuPDF raises exception -> automatically falls back to pdfplumber successfully."""
    valid_pdf = tmp_path / "sample_paper.pdf"
    _create_minimal_valid_pdf(valid_pdf, "This text will be read by pdfplumber during fallback.")

    with patch("src.utils.pdf_text._extract_pages_pymupdf", side_effect=RuntimeError("PyMuPDF engine crashed")):
        res = extract_document(valid_pdf)
        assert res.status == "OK"
        assert res.method == "pdfplumber"
        assert res.total_chars > 50


# ── Test G: Both Parsers Fail ─────────────────────────────────────────────────

def test_g_both_parsers_fail(tmp_path: Path):
    """Test G: Both parsers fail -> controlled failure without crashing graph."""
    broken_pdf = tmp_path / "double_failure.pdf"
    broken_pdf.write_bytes(b"%PDF-1.4\nBroken body\n%%EOF" * 10)

    with patch("src.utils.pdf_text._extract_pages_pymupdf", side_effect=Exception("PyMuPDF error")), \
         patch("src.utils.pdf_text._extract_pages_pdfplumber", side_effect=Exception("pdfplumber error")):
        res = extract_document(broken_pdf)
        assert res.status == "PDF_PARSE_FAILED"
        assert res.method == "abstract_only"
        assert res.total_chars == 0


# ── Test H: Network Timeout ───────────────────────────────────────────────────

def test_h_network_timeout():
    """Test H: Network timeout during download -> controlled PDF_DOWNLOAD_FAILED."""
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        path, status, err, meta = download_pdf_full("test_timeout_id", "https://arxiv.org/pdf/timeout.pdf", max_attempts=1)
        assert path is None
        assert status == "PDF_DOWNLOAD_FAILED"
        assert "timed out" in (err or "").lower() or "network failure" in (err or "").lower()


# ── Test I: HTTP 429 Retry and Backoff ────────────────────────────────────────

def test_i_http_429_rate_limiting():
    """Test I: HTTP 429 response -> handles backoff gracefully."""
    mock_headers = MagicMock()
    mock_headers.get.return_value = "1"  # Retry-After: 1s
    err = urllib.error.HTTPError("https://arxiv.org/pdf/429.pdf", 429, "Too Many Requests", mock_headers, None)

    with patch("urllib.request.urlopen", side_effect=err), \
         patch("time.sleep") as mock_sleep:
        path, status, error, meta = download_pdf_full("test_429_id", max_attempts=2)
        assert path is None
        assert status == "PDF_DOWNLOAD_FAILED"
        assert "429" in (error or "")
        assert mock_sleep.called


# ── Test J: Valid Existing Cache ──────────────────────────────────────────────

def test_j_valid_cache_reused(tmp_path: Path):
    """Test J: Existing valid PDF in cache is reused without redownloading."""
    cached_pdf = tmp_path / "cached_paper.pdf"
    _create_minimal_valid_pdf(cached_pdf, "Cached paper content.")

    with patch("src.utils.pdf_text.PDF_DIR", tmp_path), \
         patch("urllib.request.urlopen") as mock_urlopen:
        path, status, err, meta = download_pdf_full("cached_paper")
        assert path == cached_pdf
        assert status == "OK"
        assert meta["cached"] is True
        # Verify no network request was dispatched
        mock_urlopen.assert_not_called()


# ── Embedding Safety Verification ─────────────────────────────────────────────

def test_embedding_safety_on_empty_text():
    """Verify chunk_embed_node returns controlled error on empty sections."""
    paper = PaperMeta(arxiv_id="empty.text.paper", title="Empty Paper")
    state = AgentState(selected_paper=paper, sections={})
    res = chunk_embed_node(state)
    assert res["n_chunks"] == 0
    assert res["collection_name"] is None
    assert "No usable text was extracted from the PDF." in res["errors"]
