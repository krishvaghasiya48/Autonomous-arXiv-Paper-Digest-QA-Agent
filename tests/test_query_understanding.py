"""Tests for Node 1 — Query Understanding.

Validates the 6 essential test cases:
  1. Bare arXiv ID (e.g. "2401.12345")
  2. Versioned arXiv ID (e.g. "2401.12345v2")
  3. arXiv abstract URL (e.g. "https://arxiv.org/abs/2401.12345")
  4. arXiv PDF URL (e.g. "https://arxiv.org/pdf/2401.12345.pdf")
  5. Plain research topic (e.g. "KV-cache compression for LLMs")
  6. Empty or whitespace string
"""

from unittest.mock import patch
import pytest

from src.nodes.query_understanding import query_understanding_node
from src.state import AgentState


def test_bare_arxiv_id():
    state = AgentState(raw_input="2401.12345")
    res = query_understanding_node(state)
    assert res["intent"] == "paper_lookup"
    assert res["arxiv_id"] == "2401.12345"
    assert res["parsed_query"] is None


def test_versioned_arxiv_id():
    state = AgentState(raw_input="2401.12345v3")
    res = query_understanding_node(state)
    assert res["intent"] == "paper_lookup"
    assert res["arxiv_id"] == "2401.12345"  # Version suffix stripped
    assert res["parsed_query"] is None


def test_abs_url():
    state = AgentState(raw_input="https://arxiv.org/abs/2401.12345")
    res = query_understanding_node(state)
    assert res["intent"] == "paper_lookup"
    assert res["arxiv_id"] == "2401.12345"


def test_pdf_url():
    state = AgentState(raw_input="https://arxiv.org/pdf/2401.12345.pdf")
    res = query_understanding_node(state)
    assert res["intent"] == "paper_lookup"
    assert res["arxiv_id"] == "2401.12345"


def test_plain_topic():
    mock_json = '{"intent": "topic_search", "cleaned_query": "KV-cache compression for LLMs", "arxiv_id": null}'
    with patch("src.services.llm.call_llm", return_value=mock_json):
        state = AgentState(raw_input="KV-cache compression for LLMs")
        res = query_understanding_node(state)
        assert res["intent"] == "topic_search"
        assert res["arxiv_id"] is None
        assert "KV-cache" in res["parsed_query"]


def test_empty_input():
    state = AgentState(raw_input="   ")
    res = query_understanding_node(state)
    assert res["intent"] == "topic_search"
    assert res["arxiv_id"] is None
