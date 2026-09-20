"""Node 2a / 2b — arXiv Retrieval.

Node 2a: arxiv_retrieval_topic_node
    Reads  : state.parsed_query
    Writes : state.candidates[]
    Edge   : 0 results → clarify;  >0 results → selection

Node 2b: arxiv_retrieval_id_node
    Reads  : state.arxiv_id
    Writes : state.selected_paper  (skips selection/ranking entirely)
    Edge   : always → fetch_parse
"""

from __future__ import annotations

from src.services.arxiv_client import by_id, search, broadened_suggestions
from src.state import AgentState
from src.utils.logging import log_stage


def arxiv_retrieval_topic_node(state: AgentState) -> dict:
    """Topic search — returns candidates list for the selection node."""
    query = state.parsed_query or state.raw_input or ""

    try:
        candidates = search(query)
    except Exception as exc:
        log_stage("arXiv API", ok=False, reason=str(exc))
        return {
            "node_trace": ["arxiv_retrieval_topic"],
            "candidates": [],
            "errors": [f"arXiv search failed: {exc}"],
        }

    if not candidates:
        suggestions = broadened_suggestions(query)
        log_stage("arXiv API", ok=True, reason="Zero results; generated clarification suggestions")
        return {
            "node_trace": ["arxiv_retrieval_topic"],
            "candidates": [],
            "clarification_suggestions": suggestions,
        }

    log_stage("arXiv API", ok=True, reason=f"Retrieved {len(candidates)} candidates")
    return {
        "node_trace": ["arxiv_retrieval_topic"],
        "candidates": candidates,
    }


def arxiv_retrieval_id_node(state: AgentState) -> dict:
    """Direct ID lookup — sets selected_paper, bypassing ranking."""
    arxiv_id = state.arxiv_id or ""

    if not arxiv_id:
        log_stage("arXiv API", ok=False, reason="Empty arXiv ID provided")
        return {
            "node_trace": ["arxiv_retrieval_id"],
            "selected_paper": None,
            "errors": ["Validation error: Empty arXiv ID provided."],
        }

    try:
        paper = by_id(arxiv_id)
    except Exception as exc:
        log_stage("arXiv API", ok=False, reason=str(exc))
        return {
            "node_trace": ["arxiv_retrieval_id"],
            "selected_paper": None,
            "errors": [f"arXiv ID lookup failed for {arxiv_id}: {exc}"],
        }

    if paper is None:
        log_stage("arXiv API", ok=False, reason=f"No arXiv record found for ID: {arxiv_id}")
        return {
            "node_trace": ["arxiv_retrieval_id"],
            "selected_paper": None,
            "errors": [f"Validation error: No arXiv record found for ID: {arxiv_id}"],
        }

    log_stage("arXiv API", ok=True, reason=f"Found '{paper.title[:45]}...'")
    return {
        "node_trace": ["arxiv_retrieval_id"],
        "selected_paper": paper,
    }
