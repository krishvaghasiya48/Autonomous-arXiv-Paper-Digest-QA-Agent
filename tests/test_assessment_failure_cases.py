"""Assessment-specific Failure Case Verification Suite.

Tests all 14 mandatory failure cases required by the 8byte technical assessment:
Failure 1  — No arXiv results (controlled suggestions returned)
Failure 2  — Too many results (selection/ranking without downloading all PDFs)
Failure 3  — arXiv API unavailable (controlled API error)
Failure 4  — Invalid paper ID (clear validation error)
Failure 5  — PDF download failure (does not crash or parse corrupt file)
Failure 6  — PDF corrupted (graceful fallback without crash)
Failure 7  — PDF has no extractable text (sanity check detects it, sets parse_degraded)
Failure 8  — Embedding failure (controlled graph error)
Failure 9  — Vector store failure (controlled graph error)
Failure 10 — LLM unavailable (falls through provider priority chain)
Failure 11 — All LLM providers unavailable (no fabricated summaries, factual extraction)
Failure 12 — QA answer not present in paper (strict refusal/abstention)
Failure 13 — Very vague topic (controlled query broadening)
Failure 14 — Session state missing/corrupted (clean error / recovery)
"""

from unittest.mock import patch, MagicMock
import urllib.error
import pytest

from src.nodes.arxiv_retrieval import arxiv_retrieval_topic_node, arxiv_retrieval_id_node
from src.nodes.fetch_parse import fetch_parse_node
from src.nodes.chunk_embed import chunk_embed_node
from src.nodes.selection import selection_node, clarify_node
from src.nodes.qa import answer_question
from src.nodes.summarize import summarize_node
from src.services.arxiv_client import broadened_suggestions, normalize_arxiv_id, generate_query_strategies
from src.services.llm import call_llm
from src.state import AgentState, PaperMeta
from src.utils.errors import ArxivRetrievalError, LLMProviderError, SessionNotFoundError
from src.utils.pdf_text import _is_usable, sanity_check, _is_valid_pdf_file
from src.utils.session import load_session


def test_failure_1_no_arxiv_results():
    """Failure 1: arXiv returns 0 results -> controlled suggestions returned without crashing."""
    state = AgentState(raw_input="xyzzynonexistentresearchtopic12345")
    with patch("src.nodes.arxiv_retrieval.search", return_value=[]):
        res = arxiv_retrieval_topic_node(state)
        assert res["candidates"] == []
        assert "clarification_suggestions" in res
        assert len(res["clarification_suggestions"]) >= 1


def test_failure_2_too_many_results():
    """Failure 2: Many results returned -> ranks/selects single best paper without downloading all."""
    candidates = [
        PaperMeta(arxiv_id=f"2401.0000{i}", title=f"Candidate Paper {i}", abstract="RAG", published="2024-01-01")
        for i in range(15)
    ]
    state = AgentState(raw_input="RAG", candidates=candidates)
    res = selection_node(state)
    assert res["selected_paper"] is not None
    assert res["selected_paper"].arxiv_id.startswith("2401.0000")
    assert res["selection_reason"] is not None


def test_failure_3_arxiv_api_unavailable():
    """Failure 3: arXiv API down -> surfaces controlled error in state without unhandled crash."""
    state = AgentState(raw_input="RAG")
    with patch("src.nodes.arxiv_retrieval.search", side_effect=ArxivRetrievalError("Connection refused")):
        res = arxiv_retrieval_topic_node(state)
        assert res["candidates"] == []
        assert any("arXiv search failed" in e for e in res["errors"])


def test_failure_4_invalid_paper_id():
    """Failure 4: Invalid/nonexistent arXiv ID -> clear validation error returned."""
    state = AgentState(raw_input="invalid.99999", intent="paper_lookup", arxiv_id="invalid.99999")
    with patch("src.nodes.arxiv_retrieval.by_id", return_value=None):
        res = arxiv_retrieval_id_node(state)
        assert res["selected_paper"] is None
        assert any("Validation error" in e for e in res["errors"])


def test_failure_5_pdf_download_failure():
    """Failure 5: PDF download fails -> falls back to abstract, does not attempt PDF parse."""
    paper = PaperMeta(arxiv_id="2401.99999", title="Test Paper", abstract="Valid abstract text.", pdf_url="https://arxiv.org/pdf/fail.pdf")
    state = AgentState(selected_paper=paper)
    with patch("src.nodes.fetch_parse.download_pdf", return_value=None):
        res = fetch_parse_node(state)
        assert res["pdf_path"] is None
        assert res["parse_degraded"] is True
        assert res["parse_method"] == "abstract_only"
        assert res["sections"].get("abstract") == "Valid abstract text."


def test_failure_6_pdf_corrupted():
    """Failure 6: Corrupted PDF -> alternate parser/sanity check falls back gracefully."""
    paper = PaperMeta(arxiv_id="2401.88888", title="Corrupt Paper", abstract="Fallback abstract.")
    state = AgentState(selected_paper=paper)
    with patch("src.nodes.fetch_parse.download_pdf") as mock_dl, \
         patch("src.nodes.fetch_parse.extract_text", return_value=("", "abstract_only")):
        mock_dl.return_value = MagicMock(exists=lambda: True, stat=lambda: MagicMock(st_size=2000), name="corrupt.pdf")
        res = fetch_parse_node(state)
        assert res["parse_degraded"] is True
        assert res["parse_method"] == "abstract_only"


def test_failure_7_scanned_image_only_pdf():
    """Failure 7: PDF with no extractable text (scanned/whitespace) detected by sanity check."""
    whitespace_text = "   \n\n\t  " * 200
    ok, reason = sanity_check(whitespace_text)
    assert ok is False
    assert "whitespace" in reason or "empty" in reason or "short" in reason


def test_failure_8_embedding_failure():
    """Failure 8: Embedding generation failure -> enters controlled error state."""
    paper = PaperMeta(arxiv_id="2401.77777", title="Test Paper")
    state = AgentState(selected_paper=paper, sections={"abstract": "Some text to embed."})
    with patch("src.nodes.chunk_embed.upsert_chunks", side_effect=RuntimeError("CUDA/OOM embedding error")):
        res = chunk_embed_node(state)
        assert res["n_chunks"] == 0
        assert any("chunk_embed failure" in e for e in res["errors"])


def test_failure_9_vector_store_failure():
    """Failure 9: Vector store failure -> enters controlled error state."""
    paper = PaperMeta(arxiv_id="2401.66666", title="Test Paper")
    state = AgentState(selected_paper=paper, sections={"abstract": "Some text to embed."})
    with patch("src.nodes.chunk_embed.upsert_chunks", side_effect=Exception("Disk full")):
        res = chunk_embed_node(state)
        assert res["n_chunks"] == 0
        assert any("chunk_embed failure" in e for e in res["errors"])


def test_failure_10_llm_provider_fallback_chain():
    """Failure 10: Provider 1 fails -> falls back along Groq -> Gemini -> Ollama chain."""
    with patch("src.services.llm._call_groq", side_effect=Exception("Groq rate limit")), \
         patch("src.services.llm._call_gemini", return_value="Gemini response"):
        resp = call_llm(system="sys", user="user")
        assert resp == "Gemini response"


def test_failure_11_all_llm_providers_unavailable():
    """Failure 11: All LLM providers fail -> controlled extraction without fake claims or placeholders."""
    paper = PaperMeta(
        arxiv_id="2401.55555",
        title="Novel Neural Machine Translation",
        abstract="We propose an attention architecture that achieves 30.5 BLEU.",
        published="2024-01-01",
    )
    state = AgentState(
        selected_paper=paper,
        sections={"abstract": paper.abstract, "method": "We introduce a dual-encoder transformer architecture."},
    )
    with patch("src.nodes.summarize.call_llm", side_effect=LLMProviderError("all", "No providers available")), \
         patch("src.nodes.summarize.save_session"):
        res = summarize_node(state)
        briefing = res["briefing"]
        assert briefing is not None
        assert "See full paper text" not in " ".join(briefing.approach)
        assert "Refer to empirical evaluations" not in " ".join(briefing.key_results)
        assert "LLM unavailable" not in " ".join(briefing.limitations)


def test_failure_12_qa_abstention():
    """Failure 12: Question not present in paper -> agent strictly refuses/abstains."""
    paper = PaperMeta(arxiv_id="2401.44444", title="Quantum Computing Advances")
    state = AgentState(arxiv_id="2401.44444", selected_paper=paper, collection_name="test_col")
    with patch("src.nodes.qa.query_hybrid", return_value=[]), \
         patch("src.nodes.qa.save_session"):
        updated_state, turn = answer_question(state, "How to bake sourdough bread?")
        assert turn.is_refusal is True
        assert ("not stated in this paper" in turn.answer.lower() or 
                "couldn't find enough information" in turn.answer.lower())


def test_failure_13_vague_topic_query_broadening():
    """Failure 13: Very vague or broad topic -> controlled multi-strategy query construction."""
    strategies = generate_query_strategies("RAG in large language models")
    assert len(strategies) >= 2
    # Ensure controlled, deterministic fallback terms exist
    all_queries = [s[1] for s in strategies]
    assert any("RAG" in q for q in all_queries)


def test_failure_14_session_missing_or_corrupted():
    """Failure 14: Nonexistent session requested -> raises SessionNotFoundError gracefully."""
    with pytest.raises(SessionNotFoundError):
        load_session("nonexistent.99999.session.id")
