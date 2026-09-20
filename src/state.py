"""Shared state schema — the single object that flows through every graph node.

Design note
-----------
Vectors live on disk in Chroma.  This object holds only a *collection_name*
pointing at them, so the whole state serialises cheaply to
  data/sessions/<arxiv_id>.json
and QA can resume in a new process without re-parsing or re-embedding.
That is the answer to spec question §5.4.

Every node reads from and writes to an AgentState instance.  LangGraph
passes it as a dict between nodes; we annotate with `Annotated` reducers
where lists need merging rather than replacing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
import operator

from pydantic import BaseModel, Field


# ── Sub-models ────────────────────────────────────────────────────────────────

class PaperMeta(BaseModel):
    """Normalised record from the arXiv API."""
    arxiv_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    pdf_url: str = ""
    abs_url: str = ""
    categories: list[str] = Field(default_factory=list)
    published: str = ""   # ISO-8601 date string
    updated: str = ""


class QATurn(BaseModel):
    """One question-answer exchange in the QA loop."""
    question: str
    answer: str
    chunk_ids: list[str] = Field(default_factory=list)   # [C1, C3, ...]
    is_refusal: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Briefing(BaseModel):
    """Structured executive briefing — schema-locked LLM output.

    The `limitations` field is mandatory; if the LLM returns it empty
    the summarize node re-prompts once.
    """
    title: str
    authors: list[str] = Field(default_factory=list)
    arxiv_id: str
    published: str
    link: str

    # Core content — all required
    significance: str = Field(
        description="1-paragraph plain-English summary explaining why this paper matters"
    )
    problem_statement: str = Field(
        description="Clear description of the problem this paper addresses"
    )
    approach: list[str] = Field(
        default_factory=list,
        description="Method/approach as bullet points"
    )
    key_results: list[str] = Field(
        default_factory=list,
        description="Main results and claims"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Explicit limitations — mandatory, never empty"
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="3–5 suggested follow-up questions a reader might ask"
    )

    # Parse quality metadata — surfaced in output banner
    parse_degraded: bool = False
    parse_method: Literal["pymupdf", "pdfplumber", "abstract_only"] = "pymupdf"
    n_chunks: int = 0
    selection_reason: str = ""

    def to_markdown(self) -> str:
        """Render briefing as human-readable Markdown."""
        warn = ""
        if self.parse_degraded:
            warn = (
                "\n> ⚠️  **Parse degraded** — PDF could not be fully extracted "
                f"(method: `{self.parse_method}`). "
                "Briefing is based on abstract + metadata only.\n"
            )

        bullet = lambda items: "\n".join(f"- {i}" for i in items) if items else "- N/A"

        return f"""# {self.title}

**Authors:** {', '.join(self.authors)}
**arXiv ID:** [{self.arxiv_id}]({self.link})
**Published:** {self.published}
{warn}
---

## Why This Paper Matters
{self.significance}

## Problem Statement
{self.problem_statement}

## Method / Approach
{bullet(self.approach)}

## Key Results
{bullet(self.key_results)}

## Limitations
{bullet(self.limitations)}

## Suggested Follow-up Questions
{bullet(self.follow_up_questions)}
"""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


# ── Shared graph state ────────────────────────────────────────────────────────

class AgentState(BaseModel):
    """
    The single object shared across all graph nodes.

    LangGraph represents state as a TypedDict internally, but we keep a
    Pydantic model for validation + easy JSON serialisation.

    Persistence
    -----------
    After the summarise node completes, the full state is written to
      data/sessions/<arxiv_id>.json
    The `ask` CLI command hydrates from that file — no re-parsing,
    no re-embedding.

    node_trace
    ----------
    Every node appends its own name on entry.  This gives free
    observability: print state.node_trace to see the execution path.
    The list uses Annotated[list, operator.add] so LangGraph merges
    rather than replaces on update.
    """

    # ── Input ─────────────────────────────────────────────────────────────────
    raw_input: str = ""
    intent: Literal["topic_search", "paper_lookup"] | None = None
    parsed_query: str | None = None   # cleaned topic string
    arxiv_id: str | None = None       # set when intent == paper_lookup

    # ── Retrieval ─────────────────────────────────────────────────────────────
    candidates: list[PaperMeta] = Field(default_factory=list)
    selected_paper: PaperMeta | None = None
    selection_reason: str | None = None

    # ── Parsing ───────────────────────────────────────────────────────────────
    pdf_path: str | None = None
    # sections dict: 'abstract' -> text, 'introduction' -> text, ...
    sections: dict[str, str] = Field(default_factory=dict)
    page_section_map: dict[str, list[tuple[int, str]]] = Field(default_factory=dict)
    parse_method: Literal["pymupdf", "pdfplumber", "abstract_only"] | None = None
    parse_degraded: bool = False
    pdf_status: str | None = None  # "OK", "PDF_DOWNLOAD_FAILED", "PDF_INVALID", "PDF_CORRUPTED", "PDF_PARSE_FAILED", "PDF_TEXT_EMPTY", "PDF_SCANNED", "PDF_PARSE_DEGRADED"

    # ── Vector store (reference only — vectors live on disk) ──────────────────
    collection_name: str | None = None
    n_chunks: int = 0

    # ── Output ────────────────────────────────────────────────────────────────
    briefing: Briefing | None = None
    # qa_history uses add reducer so turns accumulate across loop iterations
    qa_history: Annotated[list[QATurn], operator.add] = Field(default_factory=list)

    # ── Control ───────────────────────────────────────────────────────────────
    errors: Annotated[list[str], operator.add] = Field(default_factory=list)
    # node_trace uses add reducer so every node's append is preserved
    node_trace: Annotated[list[str], operator.add] = Field(default_factory=list)

    # Clarification suggestions — set when arXiv returns zero results
    clarification_suggestions: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
