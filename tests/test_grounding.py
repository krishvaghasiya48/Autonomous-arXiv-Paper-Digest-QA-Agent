"""Tests for Grounded QA & Strict Refusal Behavior (Phase 2.4).

Validates:
  1. The agent refuses out-of-scope questions with the exact refusal string:
     "Not stated in this paper."
  2. The QATurn is flagged with is_refusal=True when refusal occurs.
  3. Grounded answers properly attach citation tags ([C1], [C2]).
"""

from unittest.mock import patch

from src.nodes.qa import answer_question
from src.prompts.qa import EXACT_REFUSAL_STRING
from src.state import AgentState, PaperMeta


def test_qa_refusal_on_empty_chunks():
    paper = PaperMeta(
        arxiv_id="test.0001",
        title="Test Attention Paper",
        abstract="We propose the Transformer.",
    )
    state = AgentState(
        arxiv_id="test.0001",
        selected_paper=paper,
        collection_name="nonexistent_empty_collection_test",
    )

    with patch("src.nodes.qa.save_session"):
        updated_state, turn = answer_question(
            state,
            "What are the ingredients of chocolate chip cookies according to this paper?"
        )

    assert turn.is_refusal is True
    assert EXACT_REFUSAL_STRING in turn.answer


def test_qa_refusal_when_llm_signals_absence():
    paper = PaperMeta(
        arxiv_id="test.0001",
        title="Test Attention Paper",
        abstract="We propose the Transformer.",
    )
    state = AgentState(
        arxiv_id="test.0001",
        selected_paper=paper,
        collection_name="test_collection",
    )

    mock_llm_answer = (
        f"{EXACT_REFUSAL_STRING} The provided context focuses exclusively on machine translation "
        "and multi-head attention mechanisms, without mentioning computer vision datasets."
    )

    with patch("src.nodes.qa.query_hybrid") as mock_query, \
         patch("src.nodes.qa.call_llm", return_value=mock_llm_answer), \
         patch("src.nodes.qa.save_session"):

        mock_query.return_value = [
            {"chunk_id": "test_0001::method::0", "text": "Multi-head attention maps queries...", "metadata": {}}
        ]

        updated_state, turn = answer_question(state, "How does this paper benchmark ImageNet classification?")

        assert turn.is_refusal is True
        assert turn.answer.startswith(EXACT_REFUSAL_STRING)


def test_qa_grounded_answer_with_citations():
    paper = PaperMeta(
        arxiv_id="test.0001",
        title="Test Attention Paper",
    )
    state = AgentState(
        arxiv_id="test.0001",
        selected_paper=paper,
        collection_name="test_collection",
    )

    mock_llm_answer = (
        "The model uses 8 parallel attention layers or heads [C1], where each has dimension d_k = 64 [C2]."
    )

    with patch("src.nodes.qa.query_hybrid") as mock_query, \
         patch("src.nodes.qa.call_llm", return_value=mock_llm_answer), \
         patch("src.nodes.qa.save_session"):

        mock_query.return_value = [
            {"chunk_id": "test_0001::method::0", "text": "We employ h = 8 parallel attention layers.", "metadata": {}},
            {"chunk_id": "test_0001::method::1", "text": "For each we use d_k = d_v = 64.", "metadata": {}},
        ]

        updated_state, turn = answer_question(state, "How many attention heads are used?")

        assert turn.is_refusal is False
        assert len(turn.chunk_ids) == 2
        assert "[C1]" in turn.chunk_ids[0]
        assert "[C2]" in turn.chunk_ids[1]
