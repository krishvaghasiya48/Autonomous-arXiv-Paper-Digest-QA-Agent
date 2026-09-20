"""Tests for PDF Extraction Dual-Parser & Graceful Fallback (Phase 1.5).

Validates:
  1. Graceful fallback when a PDF is empty or corrupt.
  2. extract_text() returns ('', 'abstract_only') rather than raising an exception.
  3. Node 4 (fetch_parse_node) sets parse_degraded=True and retains abstract.
"""

import tempfile
from pathlib import Path

from src.nodes.fetch_parse import fetch_parse_node
from src.state import AgentState, PaperMeta
from src.utils.pdf_text import extract_text


def test_corrupt_pdf_does_not_crash(tmp_path: Path):
    # Create a broken/corrupt PDF fixture
    corrupt_pdf = tmp_path / "broken_sample.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\nCorrupted content without valid xref or trailer\n%%EOF")

    text, method = extract_text(corrupt_pdf)
    assert method == "abstract_only"
    assert text == ""


def test_empty_pdf_does_not_crash(tmp_path: Path):
    empty_pdf = tmp_path / "empty_sample.pdf"
    empty_pdf.write_bytes(b"")

    text, method = extract_text(empty_pdf)
    assert method == "abstract_only"
    assert text == ""


def test_fetch_parse_node_handles_fallback():
    # Paper pointing to nonexistent local/mock URL
    paper = PaperMeta(
        arxiv_id="9999.99999",
        title="Mock Paper on Neural Scaling",
        authors=["Alice", "Bob"],
        abstract="This paper discusses theoretical limits of loss scaling.",
        pdf_url="http://invalid-domain-that-does-not-exist.test/test.pdf",
    )
    state = AgentState(
        raw_input="9999.99999",
        intent="paper_lookup",
        arxiv_id="9999.99999",
        selected_paper=paper,
    )

    update = fetch_parse_node(state)
    assert update["parse_degraded"] is True
    assert update["parse_method"] == "abstract_only"
    assert "abstract" in update["sections"]
    assert "theoretical limits" in update["sections"]["abstract"]
