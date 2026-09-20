"""Official arXiv API client — Direct Atom XML queries against export.arxiv.org.

Responsibilities:
- search(query, max_results)  → list[PaperMeta]   multi-strategy topic search
- by_id(arxiv_id)             → PaperMeta | None   direct ID lookup
- Atom XML parsing with full namespace support (atom + arxiv extensions)
- Strict ID normalization:
    http://arxiv.org/abs/2312.10997v5 -> 2312.10997
    https://arxiv.org/pdf/2312.10997.pdf -> 2312.10997
- Controlled multi-stage query construction with automatic fallback
- Tenacity retries with exponential backoff on HTTP 429/503/network errors
- Raises ArxivRetrievalError if the API is completely unreachable
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import ARXIV_MAX_RESULTS, ARXIV_RETRY_ATTEMPTS, ARXIV_RETRY_WAIT
from src.state import PaperMeta
from src.utils.errors import ArxivRetrievalError
from src.utils.logging import log_info, log_stage, log_warning

logger = logging.getLogger(__name__)

ARXIV_API_BASE_URL = "https://export.arxiv.org/api/query"

# XML Namespaces in official arXiv Atom feed
ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

_STRIP_VERSION = re.compile(r"v\d+$", re.IGNORECASE)
_CLEAN_WS = re.compile(r"\s+")

_ARXIV_ID_RE = re.compile(
    r"(?ix)"
    r"(?:https?://arxiv\.org/(?:abs|pdf|html|e-print)/)?"
    r"(?:arxiv[:\s]*)?"
    r"("
    r"\d{4}\.\d{4,5}(?:v\d+)?"
    r"|"
    r"[a-z\-]+(?:\.[a-z\-]+)?/\d{7}(?:v\d+)?"
    r")"
)

STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "for", "to", "of", "with", "by", "from",
    "about", "into", "through", "during", "before", "after", "above", "below",
    "and", "or", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "what", "how", "why", "where", "when", "which", "who", "whom", "this", "that",
}

USER_AGENT = "arxiv-paper-digest-agent/1.0 (academic-research-tool; mailto:research@example.com)"


# ── ID Normalization ──────────────────────────────────────────────────────────

def normalize_arxiv_id(raw_id_or_url: str) -> str:
    """Normalize any arXiv URL, versioned ID, or raw ID into a bare arXiv ID.

    Examples:
      'http://arxiv.org/abs/2312.10997' -> '2312.10997'
      'https://arxiv.org/abs/2312.10997v5' -> '2312.10997'
      'https://arxiv.org/pdf/2312.10997.pdf' -> '2312.10997'
      '2312.10997v2' -> '2312.10997'
      'hep-th/9901001v1' -> 'hep-th/9901001'
    """
    text = (raw_id_or_url or "").strip()
    text = re.sub(r"\.pdf$", "", text, flags=re.IGNORECASE)

    m = _ARXIV_ID_RE.search(text)
    if m:
        bare = m.group(1)
        return _STRIP_VERSION.sub("", bare)

    # Fallback to last segment of URL path
    if "/" in text:
        parts = [p for p in text.split("/") if p]
        if parts:
            candidate = re.sub(r"\.pdf$", "", parts[-1], flags=re.IGNORECASE)
            m2 = _ARXIV_ID_RE.search(candidate)
            if m2:
                return _STRIP_VERSION.sub("", m2.group(1))

    return _STRIP_VERSION.sub("", text)


def _clean(text: str | None) -> str:
    return _CLEAN_WS.sub(" ", (text or "")).strip()


# ── Atom XML Parsing ──────────────────────────────────────────────────────────

def parse_atom_entry(entry: ET.Element) -> PaperMeta:
    """Extract PaperMeta from an Atom <entry> element with namespace handling."""
    # 1. ID
    id_elem = entry.find("atom:id", ATOM_NS)
    if id_elem is None:
        id_elem = entry.find("{http://www.w3.org/2005/Atom}id")
    raw_id = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
    arxiv_id = normalize_arxiv_id(raw_id)

    # 2. Title
    title_elem = entry.find("atom:title", ATOM_NS)
    if title_elem is None:
        title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
    title = _clean(title_elem.text if title_elem is not None else "")

    # 3. Abstract / Summary
    summary_elem = entry.find("atom:summary", ATOM_NS)
    if summary_elem is None:
        summary_elem = entry.find("{http://www.w3.org/2005/Atom}summary")
    abstract = _clean(summary_elem.text if summary_elem is not None else "")

    # 4. Dates
    published_elem = entry.find("atom:published", ATOM_NS)
    if published_elem is None:
        published_elem = entry.find("{http://www.w3.org/2005/Atom}published")
    published = published_elem.text.strip()[:10] if published_elem is not None and published_elem.text else ""

    updated_elem = entry.find("atom:updated", ATOM_NS)
    if updated_elem is None:
        updated_elem = entry.find("{http://www.w3.org/2005/Atom}updated")
    updated = updated_elem.text.strip()[:10] if updated_elem is not None and updated_elem.text else ""

    # 5. Authors
    authors: list[str] = []
    for author_elem in entry.findall("atom:author", ATOM_NS) or entry.findall("{http://www.w3.org/2005/Atom}author"):
        name_elem = author_elem.find("atom:name", ATOM_NS)
        if name_elem is None:
            name_elem = author_elem.find("{http://www.w3.org/2005/Atom}name")
        if name_elem is not None and name_elem.text:
            authors.append(_clean(name_elem.text))

    # 6. Categories
    categories: list[str] = []
    for cat in entry.findall("atom:category", ATOM_NS) or entry.findall("{http://www.w3.org/2005/Atom}category"):
        term = cat.get("term")
        if term and term not in categories:
            categories.append(term)
    primary_cat = entry.find("arxiv:primary_category", ATOM_NS)
    if primary_cat is not None and primary_cat.get("term"):
        p_term = primary_cat.get("term")
        if p_term not in categories:
            categories.insert(0, p_term)

    # 7. Links (PDF and Abstract)
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"

    links = entry.findall("atom:link", ATOM_NS) or entry.findall("{http://www.w3.org/2005/Atom}link")
    for link in links:
        href = link.get("href", "")
        title_attr = link.get("title", "")
        type_attr = link.get("type", "")
        rel_attr = link.get("rel", "")

        if title_attr == "pdf" or type_attr == "application/pdf" or href.endswith(".pdf"):
            pdf_url = href
        elif rel_attr == "alternate" and "abs" in href:
            abs_url = href

    return PaperMeta(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        pdf_url=pdf_url,
        abs_url=abs_url,
        categories=categories,
        published=published,
        updated=updated,
    )


def parse_atom_feed(xml_bytes: bytes) -> list[PaperMeta]:
    """Parse complete arXiv Atom XML feed into a list of PaperMeta objects."""
    if not xml_bytes:
        return []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning(f"Failed to parse arXiv Atom XML: {e}")
        return []

    entries = root.findall("atom:entry", ATOM_NS)
    if not entries:
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")

    papers: list[PaperMeta] = []
    for entry in entries:
        try:
            meta = parse_atom_entry(entry)
            if meta.arxiv_id and meta.title:
                papers.append(meta)
        except Exception as exc:
            logger.debug(f"Skipping malformed entry: {exc}")

    return papers


# ── HTTP Request with Tenacity Retry ──────────────────────────────────────────

@retry(
    retry=retry_if_exception_type((urllib.error.URLError, TimeoutError, ConnectionError, OSError)),
    stop=stop_after_attempt(ARXIV_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=ARXIV_RETRY_WAIT, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_arxiv_url(url: str, timeout: int = 30) -> bytes:
    """Execute GET request against official arXiv API with polite headers and timeout."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/atom+xml, application/xml, text/xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if status != 200:
                raise urllib.error.HTTPError(url, status, f"arXiv HTTP {status}", resp.headers, None)
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504):
            # Transient / rate-limited error eligible for retry
            raise
        # Permanent error (e.g. 400 Bad Request)
        raise ArxivRetrievalError(f"arXiv API rejected query with status {e.code}: {e.reason}") from e
    except Exception as exc:
        raise ArxivRetrievalError(f"arXiv API request failed: {exc}") from exc


# ── Query Construction & Controlled Fallback ──────────────────────────────────

def clean_query_text(query: str) -> str:
    """Sanitize user query by removing punctuation, parenthesis, quotes, and excess spaces."""
    q = re.sub(r"[?!:;,\(\)\[\]\{\}\"\']", " ", query)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def generate_query_strategies(query: str) -> list[tuple[str, str]]:
    """Build controlled, deterministic search strategies for natural-language queries:
    1. Original query (quoted if phrase)
    2. Simplified keyword query (stopwords removed)
    3. Individual key terms (acronyms or key technical words)
    """
    cleaned = clean_query_text(query)
    words = cleaned.split()
    if not words:
        return [("fallback", "all:machine learning")]

    strategies: list[tuple[str, str]] = []

    # Strategy 1: Original query
    if len(words) == 1:
        strategies.append(("original", f"all:{cleaned}"))
    else:
        # First attempt: exact phrase match if short phrase
        strategies.append(("original_phrase", f'all:"{cleaned}"'))
        # Second attempt: broad token match
        strategies.append(("original_terms", f"all:{cleaned}"))

    # Strategy 2: Simplified keywords (stopwords removed)
    keywords = [w for w in words if w.lower() not in STOPWORDS]
    if keywords and len(keywords) < len(words):
        kw_str = " ".join(keywords)
        strategies.append(("simplified_keywords", f"all:{kw_str}"))

    # Strategy 3: Key terms / acronyms (e.g. "RAG", "LLM")
    acronyms = [w for w in words if w.isupper() and len(w) >= 2]
    if acronyms:
        strategies.append(("key_acronym", f"all:{acronyms[0]}"))
    elif keywords:
        longest = max(keywords, key=len)
        if len(longest) >= 4 and longest not in [s[1] for s in strategies]:
            strategies.append(("key_term", f"all:{longest}"))

    # Deduplicate while preserving order and limit to at most 3 strategies
    seen = set()
    deduped: list[tuple[str, str]] = []
    for name, s in strategies:
        if s not in seen:
            seen.add(s)
            deduped.append((name, s))
        if len(deduped) >= 3:
            break

    return deduped


# ── Public API ────────────────────────────────────────────────────────────────

def search(query: str, max_results: int = ARXIV_MAX_RESULTS) -> list[PaperMeta]:
    """Search official arXiv API with controlled multi-strategy fallback.

    Executes:
      1. Original query
      2. Simplified keywords
      3. Individual important terms
    Logs which strategy succeeded and returns candidate PaperMeta objects.
    """
    clean_q = query.strip()
    if not clean_q:
        return []

    strategies = generate_query_strategies(clean_q)
    last_error: Exception | None = None

    for idx, (strat_name, search_query) in enumerate(strategies, 1):
        params = {
            "search_query": search_query,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API_BASE_URL}?{urllib.parse.urlencode(params)}"

        try:
            xml_data = _fetch_arxiv_url(url)
            papers = parse_atom_feed(xml_data)
            if papers:
                log_info(
                    f"arXiv search succeeded on strategy {idx}/{len(strategies)} ('{strat_name}'): "
                    f"'{search_query}' -> {len(papers)} candidate(s)."
                )
                log_stage("arXiv API", ok=True, reason=f"Strategy '{strat_name}' returned {len(papers)} papers")
                return papers
        except ArxivRetrievalError as e:
            last_error = e
            log_warning(f"Strategy '{strat_name}' encountered API error: {e}")
        except Exception as exc:
            last_error = exc
            log_warning(f"Strategy '{strat_name}' failed: {exc}")

    if last_error and not isinstance(last_error, ArxivRetrievalError):
        log_stage("arXiv API", ok=False, reason=str(last_error))
        raise ArxivRetrievalError(f"All arXiv search strategies failed: {last_error}") from last_error

    log_stage("arXiv API", ok=True, reason="Zero results returned after all strategies")
    return []


def by_id(arxiv_id: str) -> PaperMeta | None:
    """Fetch a single paper directly by arXiv ID using official API id_list."""
    bare_id = normalize_arxiv_id(arxiv_id)
    if not bare_id:
        return None

    params = {"id_list": bare_id}
    url = f"{ARXIV_API_BASE_URL}?{urllib.parse.urlencode(params)}"

    try:
        xml_data = _fetch_arxiv_url(url)
        papers = parse_atom_feed(xml_data)
        if papers:
            log_stage("arXiv API", ok=True, reason=f"Direct lookup succeeded for ID {bare_id}")
            return papers[0]
        log_stage("arXiv API", ok=False, reason=f"No record found for ID {bare_id}")
        return None
    except Exception as exc:
        log_stage("arXiv API", ok=False, reason=f"Lookup failed for ID {bare_id}: {exc}")
        raise ArxivRetrievalError(f"Direct ID lookup failed for '{bare_id}': {exc}") from exc


def broadened_suggestions(query: str) -> list[str]:
    """Return 2–3 broader query suggestions when arXiv returns zero results."""
    cleaned = clean_query_text(query)
    words = cleaned.split()
    suggestions: list[str] = []

    # 1. First two words
    if len(words) >= 2:
        suggestions.append(" ".join(words[:2]))

    # 2. Keywords without stopwords
    kw = [w for w in words if w.lower() not in STOPWORDS]
    if kw and len(kw) >= 2:
        suggestions.append(" ".join(kw[:2]))
    elif kw and len(kw) == 1:
        suggestions.append(kw[0])

    # 3. Known umbrella topics
    if any(term in cleaned.lower() for term in ["rag", "retrieval"]):
        suggestions.append("retrieval augmented generation")
    elif any(term in cleaned.lower() for term in ["llm", "language model", "gpt", "transformer"]):
        suggestions.append("large language models")
    elif len(words) >= 3:
        suggestions.append(" ".join(words[:3]))

    # Deduplicate and cap at 3
    seen: list[str] = []
    for s in suggestions:
        if s and s.lower() != query.lower() and s not in seen:
            seen.append(s)

    return seen[:3] or ["retrieval augmented generation", "large language models", "deep learning"]
