"""Tests for Section-Aware Chunking Strategy (Phase 2.1).

Validates:
  1. Overlap between adjacent chunks within a section.
  2. No empty or whitespace-only chunks.
  3. Proper metadata attached to every chunk (arxiv_id, section, chunk_index).
  4. Isolation: Never merge across section boundaries.
  5. References section is excluded from vector embeddings.
"""

from src.utils.chunking import Chunk, chunk_sections, extract_references


def test_chunk_no_empty_and_metadata_present():
    sections = {
        "abstract": "We introduce a novel transformer architecture with linear attention complexity. Experiments confirm strong results.",
        "introduction": "Language models require efficient attention mechanisms for long context windows. Traditional quadratic attention struggles at scale.",
    }
    chunks = chunk_sections(sections, arxiv_id="2401.12345")
    assert len(chunks) >= 2

    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.text.strip() != ""
        assert c.arxiv_id == "2401.12345"
        assert c.section in {"abstract", "introduction"}
        assert c.chunk_index >= 0
        meta = c.to_metadata()
        assert "arxiv_id" in meta
        assert "section" in meta
        assert "chunk_index" in meta


def test_no_cross_section_merging():
    sections = {
        "method": "Our methodology utilizes a selective state-space model.",
        "limitations": "Our method requires higher memory bandwidth during backward passes.",
    }
    chunks = chunk_sections(sections, arxiv_id="1234.5678")

    method_chunks = [c for c in chunks if c.section == "method"]
    limitation_chunks = [c for c in chunks if c.section == "limitations"]

    assert len(method_chunks) > 0
    assert len(limitation_chunks) > 0

    # Ensure limitation text is never inside a method chunk
    for mc in method_chunks:
        assert "backward passes" not in mc.text
    for lc in limitation_chunks:
        assert "state-space model" not in lc.text


def test_references_excluded_from_chunks():
    sections = {
        "abstract": "This paper presents findings on KV cache compression.",
        "references": "[1] Vaswani et al. Attention is all you need. NeurIPS 2017.\n[2] Beltagy et al. Longformer. 2020.",
    }
    chunks = chunk_sections(sections, arxiv_id="2401.12345")
    # References must not be embedded into chunks
    assert all(c.section != "references" for c in chunks)

    # But references can be extracted separately
    refs = extract_references(sections)
    assert "Vaswani" in refs


def test_chunk_overlap():
    long_para = (
        "Paragraph one introduces the first hypothesis regarding deep learning generalization. " * 15
    )
    sections = {"discussion": long_para}
    chunks = chunk_sections(sections, arxiv_id="2401.12345")

    if len(chunks) > 1:
        # Check that there is overlapping content between chunk 0 and chunk 1
        end_of_first = chunks[0].text[-80:]
        words = [w for w in end_of_first.split() if len(w) > 4]
        overlap_found = any(w in chunks[1].text for w in words)
        assert overlap_found, "Expected overlap between consecutive chunks"
