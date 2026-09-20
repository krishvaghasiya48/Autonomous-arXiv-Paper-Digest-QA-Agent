"""Node 3 — Selection / Ranking.
Node clarify — zero-results terminal.

Selection strategy
------------------
1. Score each candidate with a simple heuristic:
     recency_score   = normalised published date (0–1)
     relevance_score = title/abstract overlap with query (bag-of-words Jaccard)
     combined        = 0.6 * relevance + 0.4 * recency

2. Top-K candidates (from config) are passed to the LLM with the original
   query.  The LLM picks one and must output a one-line selection_reason.

3. If the LLM call fails, fall back to the heuristic top-1.

The selection_reason is persisted into state and appears in the briefing —
it proves the ranking was not arbitrary.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from config import ARXIV_MAX_RESULTS
from src.state import AgentState, PaperMeta

# How many candidates to pass to the LLM ranker
_LLM_TOP_K = 5


# ── Heuristic scorer ──────────────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two strings."""
    tok_a = set(re.sub(r"[^\w\s]", "", a.lower()).split())
    tok_b = set(re.sub(r"[^\w\s]", "", b.lower()).split())
    if not tok_a or not tok_b:
        return 0.0
    return len(tok_a & tok_b) / len(tok_a | tok_b)


def _recency_score(published: str) -> float:
    """Normalised date score 0–1.  Papers after 2020 get higher scores."""
    try:
        dt = datetime.strptime(published[:10], "%Y-%m-%d")
        # map 2010-01-01 → 0.0,  2030-01-01 → 1.0
        origin = datetime(2010, 1, 1)
        horizon = datetime(2030, 1, 1)
        span = (horizon - origin).days
        return max(0.0, min(1.0, (dt - origin).days / span))
    except Exception:
        return 0.5


def _heuristic_rank(candidates: list[PaperMeta], query: str) -> list[PaperMeta]:
    """Return candidates sorted by combined relevance + recency score."""
    scored = []
    for p in candidates:
        text = f"{p.title} {p.abstract}"
        rel  = _jaccard(query, text)
        rec  = _recency_score(p.published)
        score = 0.6 * rel + 0.4 * rec
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


# ── LLM ranker ────────────────────────────────────────────────────────────────

def _llm_select(
    candidates: list[PaperMeta],
    query: str,
) -> tuple[PaperMeta, str]:
    """Ask LLM to pick the best paper.  Returns (paper, reason).

    Falls back to heuristic top-1 if LLM call fails or returns bad JSON.
    """
    from src.services.llm import call_llm

    numbered = "\n".join(
        f"{i+1}. [{p.arxiv_id}] {p.title} ({p.published})\n   {p.abstract[:300]}..."
        for i, p in enumerate(candidates)
    )

    system = "You are a research assistant. Respond with valid JSON only."
    user = f"""\
Given the user query and the following candidate papers, pick the single most relevant paper.

User query: {query}

Candidates:
{numbered}

Respond with JSON exactly:
{{
  "choice": <integer 1–{len(candidates)}>,
  "reason": "<one concise sentence explaining why this paper best matches the query>"
}}

JSON:"""

    try:
        raw = call_llm(system=system, user=user, temperature=0.0, max_tokens=200)
        # Strip markdown fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned).strip()

        data   = json.loads(cleaned)
        choice = int(data["choice"]) - 1           # 0-indexed
        reason = data.get("reason", "Selected by relevance ranking.")
        if 0 <= choice < len(candidates):
            return candidates[choice], reason
    except Exception:
        pass  # fall through to heuristic

    # Heuristic fallback
    ranked = _heuristic_rank(candidates, query)
    return ranked[0], "Selected by heuristic relevance + recency score (LLM unavailable)."


# ── Node entry points ─────────────────────────────────────────────────────────

def selection_node(state: AgentState) -> dict:
    """Rank candidates and pick the best one with a documented reason."""
    from src.utils.logging import log_stage

    candidates = state.candidates
    query      = state.parsed_query or state.raw_input or ""

    if not candidates:
        log_stage("Selection", ok=False, reason="No candidates to select from")
        return {
            "node_trace": ["selection"],
            "selected_paper": None,
            "selection_reason": "No candidates available.",
        }

    # Pre-rank heuristically, pass top-K to LLM
    ranked   = _heuristic_rank(candidates, query)
    top_k    = ranked[:_LLM_TOP_K]
    paper, reason = _llm_select(top_k, query)

    log_stage("Selection", ok=True, reason=f"[{paper.arxiv_id}] {paper.title[:40]}...")
    return {
        "node_trace":      ["selection"],
        "selected_paper":  paper,
        "selection_reason": reason,
    }


def clarify_node(state: AgentState) -> dict:
    """Terminal node: surface broadened query suggestions when arXiv returns zero results."""
    from src.utils.logging import log_stage
    suggestions = state.clarification_suggestions or [
        "Try a more specific research topic",
        "Use a direct arXiv ID (e.g. 2401.12345)",
        "Check spelling of key terms",
    ]
    log_stage("Selection", ok=False, reason="Zero candidates; entering clarification state")
    return {
        "node_trace": ["clarify"],
        "clarification_suggestions": suggestions,
    }
