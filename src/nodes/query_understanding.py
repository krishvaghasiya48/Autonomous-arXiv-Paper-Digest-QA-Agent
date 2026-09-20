"""Node 1 — Query Understanding.

Strategy
--------
1. Regex first  — matches arXiv IDs and arxiv.org URLs with zero LLM cost.
   Covers the vast majority of cases.

2. LLM fallback — fires only when regex gives no signal.
   Returns JSON with intent + cleaned_query + arxiv_id.
   Strips markdown fences before parsing; falls back to topic_search on
   any parse error so the graph never crashes here.

Outputs written to state
------------------------
  intent          : 'topic_search' | 'paper_lookup'
  parsed_query    : cleaned topic string (topic_search path)
  arxiv_id        : bare ID without version (paper_lookup path)
  node_trace      : ['query_understanding']
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from src.state import AgentState

# ── Regex patterns ────────────────────────────────────────────────────────────

# New-style:  2401.12345  or  2401.12345v2
# Old-style:  hep-th/9901001  or  hep-th/9901001v1
_ARXIV_ID_RE = re.compile(
    r"(?ix)"
    r"(?:arxiv[:\s]*)?"           # optional 'arxiv:' or 'arxiv ' prefix
    r"("
    r"\d{4}\.\d{4,5}(?:v\d+)?"   # new-style  e.g. 2401.12345v2
    r"|"
    r"[a-z\-]+(?:\.[a-z\-]+)?/\d{7}(?:v\d+)?"  # old-style  e.g. hep-th/9901001
    r")"
)

_STRIP_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)


def _extract_id_from_url(text: str) -> str | None:
    """Return bare arXiv ID from an arxiv.org URL, or None."""
    if "arxiv.org" not in text.lower():
        return None
    try:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        parts = [p for p in parsed.path.split("/") if p]
        # path looks like /abs/2401.12345  or /pdf/2401.12345.pdf
        if len(parts) >= 2 and parts[0] in {"abs", "pdf", "html", "e-print"}:
            candidate = parts[1].removesuffix(".pdf")
            m = _ARXIV_ID_RE.search(candidate)
            if m:
                return _STRIP_VERSION_RE.sub("", m.group(1))
    except Exception:
        pass
    return None


def _looks_like_bare_id(text: str, matched_id: str) -> bool:
    """Guard: only treat as ID lookup if the input IS the ID, not a sentence containing one."""
    compact = re.sub(r"\s+", " ", text).strip().lower()
    bare = matched_id.lower()
    return compact in {bare, f"arxiv:{bare}", f"arxiv {bare}"}


def _regex_parse(raw: str) -> tuple[str, str | None] | None:
    """
    Returns (intent, arxiv_id_or_None) if regex is conclusive, else None.
    """
    text = raw.strip()

    # 1. arxiv.org URL
    url_id = _extract_id_from_url(text)
    if url_id:
        return "paper_lookup", url_id

    # 2. Bare arXiv ID (new-style or old-style)
    m = _ARXIV_ID_RE.search(text)
    if m and _looks_like_bare_id(text, m.group(1)):
        arxiv_id = _STRIP_VERSION_RE.sub("", m.group(1))
        return "paper_lookup", arxiv_id

    return None


def _llm_parse(raw: str) -> tuple[str, str | None, str | None]:
    """
    Call LLM for intent classification when regex gives no signal.
    Returns (intent, arxiv_id_or_None, cleaned_query_or_None).
    Falls back to ('topic_search', None, raw) on any error.
    """
    try:
        from src.services.llm import call_llm
        from src.prompts.query_parse import SYSTEM, USER_TEMPLATE

        prompt = USER_TEMPLATE.format(raw_input=raw)
        response = call_llm(system=SYSTEM, user=prompt, temperature=0.0, max_tokens=128)

        # Strip markdown fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
            cleaned = re.sub(r"```$", "", cleaned).strip()

        data = json.loads(cleaned)
        intent = data.get("intent", "topic_search")
        if intent not in {"topic_search", "paper_lookup"}:
            intent = "topic_search"
        arxiv_id = data.get("arxiv_id") or None
        if arxiv_id:
            arxiv_id = _STRIP_VERSION_RE.sub("", arxiv_id.strip())
        cleaned_query = data.get("cleaned_query") or raw
        return intent, arxiv_id, cleaned_query

    except Exception:
        # Safe default — never crash the graph here
        return "topic_search", None, raw


# ── Node entry point ──────────────────────────────────────────────────────────

def query_understanding_node(state: AgentState) -> dict:
    """Parse raw_input into intent + parsed_query / arxiv_id.

    Regex covers ~95 % of inputs at zero cost.
    LLM fires only for ambiguous natural-language that might contain an ID.
    """
    raw = (state.raw_input or "").strip()
    if not raw:
        return {
            "node_trace":   ["query_understanding"],
            "intent":       "topic_search",
            "parsed_query": "",
            "arxiv_id":     None,
        }

    result = _regex_parse(raw)

    if result is not None:
        intent, arxiv_id = result
        parsed_query = None if intent == "paper_lookup" else raw
    else:
        # LLM fallback
        intent, arxiv_id, parsed_query = _llm_parse(raw)
        if intent == "paper_lookup" and parsed_query == raw:
            parsed_query = None

    from src.utils.logging import log_stage
    log_stage("Query", ok=True, reason=f"intent={intent}, target='{arxiv_id or parsed_query}'")

    return {
        "node_trace":    ["query_understanding"],
        "intent":        intent,
        "parsed_query":  parsed_query if intent == "topic_search" else None,
        "arxiv_id":      arxiv_id      if intent == "paper_lookup" else None,
    }


def understand_query(raw_input: str) -> dict:
    """Compatibility wrapper used by external callers."""
    state = AgentState(raw_input=raw_input)
    return query_understanding_node(state)

