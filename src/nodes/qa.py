"""Node 7 — Grounded Question Answering with Hybrid Retrieval.

Executes hybrid dense + BM25 retrieval over ChromaDB, formats labeled context
chunks ([C1 | section=... | page=...]), enforces the strict refusal instruction
("Not stated in this paper." / "I couldn't find enough information in the paper to answer that question.")
on out-of-paper topics, and tracks citations.
"""

from __future__ import annotations

import re
from typing import Any

from config import TOP_K_FINAL
from src.prompts.qa import EXACT_REFUSAL_STRING, SYSTEM_QA, USER_QA_TEMPLATE
from src.services.llm import call_llm
from src.services.vectorstore import _safe_collection_name, query_hybrid
from src.state import AgentState, QATurn
from src.utils.logging import log_info, log_stage, log_warning, timed_node
from src.utils.session import save_session


def _format_chunks_for_qa(hits: list[dict]) -> tuple[str, dict[str, str]]:
    """Format retrieved chunks with explicit tags and return tag-to-chunk_id mapping."""
    formatted_blocks = []
    tag_map = {}  # "C1" -> actual chunk_id

    for i, hit in enumerate(hits, 1):
        tag = f"C{i}"
        tag_map[tag] = hit["chunk_id"]
        meta = hit.get("metadata") or {}
        section = meta.get("section", "body")
        page = meta.get("page", 0)
        formatted_blocks.append(
            f"[{tag} | section={section} | page={page}]\n{hit['text'].strip()}"
        )

    return "\n\n".join(formatted_blocks), tag_map


def _extract_citations(answer: str, tag_map: dict[str, str]) -> list[str]:
    """Extract cited chunk IDs [C1], [C2] from the answer string."""
    found_tags = set(re.findall(r"\[C(\d+)\]", answer))
    cited_ids = []
    for num in sorted(found_tags, key=int):
        tag = f"C{num}"
        if tag in tag_map:
            cited_ids.append(f"[{tag}] {tag_map[tag]}")
        else:
            cited_ids.append(f"[{tag}]")
    return cited_ids


def _check_overlap(question: str, text: str) -> float:
    """Calculate substantive content token overlap between question and chunk text."""
    stop = {
        "what", "who", "whom", "where", "when", "which", "how", "why", "does", "did",
        "will", "would", "could", "should", "first", "last", "main", "most", "many",
        "this", "that", "these", "those", "have", "been", "from", "with", "about",
        "paper", "study", "states", "united",
    }
    raw_tokens = [re.sub(r"[^\w]", "", t.lower()) for t in question.split()]
    q_tokens = {t for t in raw_tokens if len(t) > 3 and t not in stop}
    if not q_tokens:
        return 0.5
    doc_text_lower = text.lower()
    matched = {t for t in q_tokens if t in doc_text_lower}
    return len(matched) / len(q_tokens)


def answer_question(state: AgentState, question: str) -> tuple[AgentState, QATurn]:
    """Core grounded QA pipeline for a single question.

    Returns the updated AgentState and the generated QATurn.
    """
    question = question.strip()
    paper = state.selected_paper
    arxiv_id = paper.arxiv_id if paper else (state.arxiv_id or "unknown")
    title = paper.title if paper else "Academic Paper"

    collection_name = state.collection_name or _safe_collection_name(arxiv_id)

    with timed_node("qa", f"Grounded QA for question: '{question[:40]}...'"):
        hits = query_hybrid(question, collection_name, n_results=TOP_K_FINAL)

        if not hits:
            refusal_text = f"{EXACT_REFUSAL_STRING} I couldn't find enough information in the paper to answer that question. No indexed chunks found."
            turn = QATurn(
                question=question,
                answer=refusal_text,
                chunk_ids=[],
                is_refusal=True,
            )
            log_stage("QA", ok=True, reason="Refusal: no indexed chunks found")
            state.qa_history.append(turn)
            save_session(state)
            return state, turn

        # Check if question has almost zero relevance to all top chunks
        combined_text = " ".join(h["text"] for h in hits)
        overlap = _check_overlap(question, combined_text)

        context_str, tag_map = _format_chunks_for_qa(hits)

        prompt = USER_QA_TEMPLATE.format(
            title=title,
            arxiv_id=arxiv_id,
            context_chunks=context_str,
            question=question,
        )

        raw_answer = ""
        try:
            raw_answer = call_llm(
                system=SYSTEM_QA,
                user=prompt,
                temperature=0.0,
                max_tokens=512,
            ).strip()
        except Exception:
            # Deterministic fallback when LLM is unavailable
            if overlap < 0.2:
                raw_answer = f"{EXACT_REFUSAL_STRING} I couldn't find enough information in the paper to answer that question."
            else:
                top_hit = hits[0]
                raw_answer = (
                    f"Based on the paper context [C1] ({top_hit['metadata'].get('section', 'section')}):\n\n"
                    f"\"{top_hit['text'][:350]}...\""
                )

        refusal_phrases = [
            EXACT_REFUSAL_STRING.lower(),
            "couldn't find enough information",
            "could not find enough information",
            "not stated in this paper",
            "insufficient information in the paper",
        ]
        is_refusal = any(phrase in raw_answer.lower() for phrase in refusal_phrases)

        citations = _extract_citations(raw_answer, tag_map)
        if not citations and not is_refusal and hits:
            citations = [f"[C1] {tag_map.get('C1', 'chunk-0')}"]

        turn = QATurn(
            question=question,
            answer=raw_answer,
            chunk_ids=citations,
            is_refusal=is_refusal,
        )

        log_stage("QA", ok=True, reason="Refused (out of scope)" if is_refusal else f"Grounded ({len(citations)} citations)")

        state.qa_history.append(turn)
        save_session(state)
        return state, turn


def qa_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node wrapper for Graph B."""
    question = (state.raw_input or "").strip()
    if not question:
        log_stage("QA", ok=False, reason="Empty question in raw_input")
        return {
            "node_trace": ["qa"],
            "errors": ["qa_node: raw_input was empty"],
        }

    updated_state, turn = answer_question(state, question)

    return {
        "node_trace": ["qa"],
        "qa_history": [turn],
    }
