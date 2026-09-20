"""Graph A — digest pipeline (nodes 1–6).

Build this first, run it with stubs to confirm routing, then fill
nodes one by one.  The graph MUST route correctly before any LLM call
exists — building nodes before edges produces a prompt chain, which is
the exact failure mode the spec names.

Two graphs
----------
Graph A  (this file, build_digest_graph)  — nodes 1–6, runs once,
         ends at the briefing.
Graph B  (build_qa_graph)                 — node 7, a separate compiled
         loop that hydrates state from the session file.  Keeping them
         separate shows lifecycle thinking rather than bolting QA onto
         the end of a chain.

The three conditional edges that earn the 25%
---------------------------------------------
1. After node 1 (query_understanding):
      intent == paper_lookup  →  arxiv_retrieval_id   (skips ranking)
      intent == topic_search  →  arxiv_retrieval_topic

2. After node 2a (arxiv_retrieval_topic):
      candidates == []        →  clarify              (no crash)
      candidates  > 0         →  selection

3. After node 4 (fetch_parse):
      parse_degraded == True  →  chunk_embed          (abstract-only path)
      parse_degraded == False →  chunk_embed          (full PDF path)
      (both go to chunk_embed; the node itself honours parse_degraded)
      Hard fail (pdf_path is None and sections empty) → summarize directly
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.state import AgentState

# ── Import real node functions (filled in later phases) ───────────────────────
# Each node is a callable: (AgentState) -> dict[str, Any]
# The dict is merged into the shared state by LangGraph.

from src.nodes.query_understanding import query_understanding_node
from src.nodes.arxiv_retrieval import (
    arxiv_retrieval_topic_node,
    arxiv_retrieval_id_node,
)
from src.nodes.selection import selection_node, clarify_node
from src.nodes.fetch_parse import fetch_parse_node
from src.nodes.chunk_embed import chunk_embed_node
from src.nodes.summarize import summarize_node
from src.nodes.qa import qa_node


# ── Routing functions (conditional edges) ────────────────────────────────────

def _route_after_query_understanding(state: AgentState) -> str:
    """Edge 1: route on intent parsed from user input."""
    if state.intent == "paper_lookup":
        return "arxiv_retrieval_id"
    return "arxiv_retrieval_topic"


def _route_after_topic_retrieval(state: AgentState) -> str:
    """Edge 2: zero results → clarify; else → selection."""
    if not state.candidates:
        return "clarify"
    return "selection"


def _route_after_fetch_parse(state: AgentState) -> str:
    """Edge 3: always go to chunk_embed.

    The chunk_embed node checks parse_degraded and sections to decide
    whether to embed real PDF chunks or just the abstract.
    If sections is completely empty AND no pdf_path, skip straight to
    summarize (hard-fail path — abstract-only briefing).
    """
    if not state.sections and not state.pdf_path:
        return "summarize"
    return "chunk_embed"


# ── Graph A: digest pipeline ──────────────────────────────────────────────────

def build_digest_graph() -> Any:
    """Build and compile Graph A (nodes 1–6).

    Returns a compiled LangGraph runnable.
    """
    g = StateGraph(AgentState)

    # Register nodes
    g.add_node("query_understanding",      query_understanding_node)
    g.add_node("arxiv_retrieval_topic",    arxiv_retrieval_topic_node)
    g.add_node("arxiv_retrieval_id",       arxiv_retrieval_id_node)
    g.add_node("clarify",                  clarify_node)
    g.add_node("selection",                selection_node)
    g.add_node("fetch_parse",              fetch_parse_node)
    g.add_node("chunk_embed",              chunk_embed_node)
    g.add_node("summarize",                summarize_node)

    # Entry point
    g.add_edge(START, "query_understanding")

    # Conditional edge 1 — intent routing
    g.add_conditional_edges(
        "query_understanding",
        _route_after_query_understanding,
        {
            "arxiv_retrieval_topic": "arxiv_retrieval_topic",
            "arxiv_retrieval_id":    "arxiv_retrieval_id",
        },
    )

    # Conditional edge 2 — zero-results branch
    g.add_conditional_edges(
        "arxiv_retrieval_topic",
        _route_after_topic_retrieval,
        {
            "clarify":   "clarify",
            "selection": "selection",
        },
    )

    # ID retrieval always skips ranking → fetch_parse
    g.add_edge("arxiv_retrieval_id", "fetch_parse")

    # Selection → fetch_parse
    g.add_edge("selection", "fetch_parse")

    # Clarify is a terminal node for Graph A
    g.add_edge("clarify", END)

    # Conditional edge 3 — parse failure routing
    g.add_conditional_edges(
        "fetch_parse",
        _route_after_fetch_parse,
        {
            "chunk_embed": "chunk_embed",
            "summarize":   "summarize",
        },
    )

    # chunk_embed → summarize → END
    g.add_edge("chunk_embed", "summarize")
    g.add_edge("summarize",   END)

    return g.compile()


# ── Graph B: QA loop ──────────────────────────────────────────────────────────

def _route_qa_loop(state: AgentState) -> str:
    """Always loop back to qa node.  The node itself checks for 'quit'."""
    return "qa"


def build_qa_graph() -> Any:
    """Build and compile Graph B (node 7 — QA loop).

    Called by `main.py ask <arxiv_id>` after hydrating state from disk.
    Loops qa_node until the user types quit/exit.
    """
    g = StateGraph(AgentState)
    g.add_node("qa", qa_node)
    g.add_edge(START, "qa")
    g.add_edge("qa", END)   # the node signals termination via a sentinel

    return g.compile()
