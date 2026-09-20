"""FastAPI server — REST + SSE bridge between the LangGraph backend and the Next.js UI.

Endpoints
---------
POST  /api/digest            Run Graph A, stream SSE progress events
GET   /api/briefing/{id}     Return completed briefing as JSON
POST  /api/qa/{arxiv_id}     Answer one question via grounded QA
GET   /api/sessions          List all saved sessions
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.graph import build_digest_graph
from src.state import AgentState
from src.utils.session import load_session, list_sessions
from src.nodes.qa import answer_question
from src.utils.errors import SessionNotFoundError


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="arXiv Paper Digest & QA Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4028",
        "http://localhost:3000",
        "http://localhost:4029",
        "http://127.0.0.1:4029",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ─────────────────────────────────────────────────

class DigestRequest(BaseModel):
    query: str


class QARequest(BaseModel):
    question: str


# ── Helpers ───────────────────────────────────────────────────────────────────

_ARXIV_ID_RE = re.compile(r"\d{4}\.\d{4,5}(v\d+)?")


def _looks_like_arxiv_id(query: str) -> bool:
    """Heuristic: does the query look like a direct paper lookup?"""
    return bool(_ARXIV_ID_RE.search(query)) or "arxiv.org" in query.lower()


# Human-readable labels matching the UI constants
_NODE_LABELS: dict[str, str] = {
    "query_understanding": "Query Understanding",
    "arxiv_retrieval_topic": "arXiv Retrieval",
    "arxiv_retrieval_id": "arXiv Retrieval",
    "selection": "Paper Selection",
    "fetch_parse": "Fetch & Parse PDF",
    "chunk_embed": "Chunk & Embed",
    "summarize": "Generate Briefing",
    "clarify": "Clarification",
}

# Canonical node name used in the UI's ALL_NODES list
_UI_NODE: dict[str, str] = {
    "query_understanding": "query_understanding",
    "arxiv_retrieval_topic": "arxiv_retrieval",
    "arxiv_retrieval_id": "arxiv_retrieval",
    "selection": "selection",
    "fetch_parse": "fetch_parse",
    "chunk_embed": "chunk_embed",
    "summarize": "summarize",
    "clarify": "clarify",
}


def _build_candidate_dict(paper, selected_paper, selection_reason: str | None) -> dict:
    """Convert a PaperMeta into the CandidatePaper shape the UI expects."""
    is_selected = (
        selected_paper is not None and paper.arxiv_id == selected_paper.arxiv_id
    )
    return {
        "id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "pdfUrl": paper.pdf_url or f"https://arxiv.org/pdf/{paper.arxiv_id}",
        "categories": paper.categories,
        "published": paper.published,
        "selected": is_selected,
        "selectionReason": selection_reason if is_selected else None,
    }


def _build_briefing_dict(state: AgentState) -> dict:
    """Convert AgentState → camelCase briefing dict for the UI."""
    b = state.briefing
    paper = state.selected_paper

    arxiv_id = b.arxiv_id if b else (state.arxiv_id or "")
    published = (b.published if b else "")[:10]

    return {
        "title": b.title if b else (paper.title if paper else ""),
        "authors": b.authors if b else (paper.authors if paper else []),
        "arxivId": arxiv_id,
        "publishDate": published,
        "link": b.link if b else f"https://arxiv.org/abs/{arxiv_id}",
        "categories": paper.categories if paper else [],
        "significance": b.significance if b else "",
        "problemStatement": b.problem_statement if b else "",
        "approach": b.approach if b else [],
        "keyResults": b.key_results if b else [],
        "limitations": b.limitations if b else [],
        "followUpQuestions": b.follow_up_questions if b else [],
        "parseDegraded": b.parse_degraded if b else state.parse_degraded,
        "parseMethod": b.parse_method if b else (state.parse_method or "pymupdf"),
        "nChunks": b.n_chunks if b else state.n_chunks,
        "selectionReason": b.selection_reason if b else (state.selection_reason or ""),
        "truncationNote": None,
    }


def _build_qa_turn_dict(turn, question: str) -> dict:
    """Convert a QATurn to the camelCase shape the UI expects."""
    return {
        "id": f"turn-{int(time.time() * 1000)}",
        "question": question,
        "answer": turn.answer,
        "citations": turn.chunk_ids,
        "chunks": [],          # chunk text retrieval omitted for now
        "isRefusal": turn.is_refusal,
        "retrievalMethod": "hybrid",
        "timestamp": turn.timestamp,
    }


# ── SSE digest generator ──────────────────────────────────────────────────────

async def _digest_event_generator(query: str) -> AsyncGenerator[dict, None]:
    """Stream SSE events for Graph A execution.

    Strategy:
    1. Determine expected node sequence from the query heuristic.
    2. Start the graph in a thread-pool executor.
    3. While it runs, emit node_start events (one per 0.8 s) to give the
       UI something to show immediately.
    4. When the graph finishes, emit node_done + complete/clarification.
    """
    is_id_lookup = _looks_like_arxiv_id(query)

    # Nodes that will be traversed (best-guess before we see node_trace)
    expected_nodes: list[str]
    if is_id_lookup:
        expected_nodes = [
            "query_understanding",
            "arxiv_retrieval_id",
            "fetch_parse",
            "chunk_embed",
            "summarize",
        ]
    else:
        expected_nodes = [
            "query_understanding",
            "arxiv_retrieval_topic",
            "selection",
            "fetch_parse",
            "chunk_embed",
            "summarize",
        ]

    loop = asyncio.get_event_loop()

    def _run_graph() -> AgentState:
        graph = build_digest_graph()
        initial = AgentState(raw_input=query)
        result = graph.invoke(initial)
        # LangGraph returns a dict; reconstruct AgentState
        if isinstance(result, dict):
            return AgentState.model_validate(result)
        return result  # type: ignore[return-value]

    # Launch graph in background thread
    future = loop.run_in_executor(None, _run_graph)

    # Emit anticipated node_start events while graph runs
    start_times: dict[str, float] = {}
    for node in expected_nodes:
        ui_node = _UI_NODE.get(node, node)
        label = _NODE_LABELS.get(node, node)
        start_times[node] = time.time()
        print(f"[BACKEND NODE] Start anticipated: {node}", flush=True)
        print(f"[UI NODE MAP] {node} -> {ui_node}", flush=True)
        print(f"[EVENT SENT] node_start: node={ui_node}, label={label}", flush=True)
        yield {"data": f'{{"type":"node_start","node":"{ui_node}","label":"{label}"}}'}
        try:
            await asyncio.wait_for(asyncio.shield(future), timeout=0.8)
            # Graph finished early — stop emitting fake events
            break
        except asyncio.TimeoutError:
            pass
        except Exception:
            break

    # Await final graph result
    try:
        state: AgentState = await future
    except Exception as exc:
        print(f"[EVENT SENT] error: {str(exc)[:200]}", flush=True)
        yield {"data": f'{{"type":"error","message":"{str(exc)[:200]}"}}'}
        return

    # Emit node_done events for every node in the actual trace
    trace = state.node_trace or expected_nodes
    for node in trace:
        ui_node = _UI_NODE.get(node, node)
        duration_ms = int((time.time() - start_times.get(node, time.time())) * 1000)
        print(f"[BACKEND NODE] Completed: {node}", flush=True)
        print(f"[UI NODE MAP] {node} -> {ui_node}", flush=True)
        print(f"[EVENT SENT] node_done: node={ui_node}, duration_ms={max(duration_ms, 50)}", flush=True)
        yield {"data": f'{{"type":"node_done","node":"{ui_node}","duration_ms":{max(duration_ms, 50)}}}'}

    # Check for clarification path
    if state.clarification_suggestions:
        import json
        suggestions_json = json.dumps(state.clarification_suggestions)
        print(f"[EVENT SENT] clarification: {len(state.clarification_suggestions)} suggestions", flush=True)
        yield {"data": f'{{"type":"clarification","suggestions":{suggestions_json}}}'}
        return

    # Emit candidates
    if state.candidates:
        import json
        papers = [
            _build_candidate_dict(p, state.selected_paper, state.selection_reason)
            for p in state.candidates
        ]
        print(f"[BACKEND] candidates retrieved: {len(papers)}", flush=True)
        print(f"[EVENT SENT] candidates: total_found={len(state.candidates)}, papers={len(papers)}", flush=True)
        yield {
            "data": json.dumps({
                "type": "candidates",
                "node": "arxiv_retrieval",
                "candidates": papers,
                "papers": papers,
                "total_found": len(state.candidates),
            })
        }

    # Emit complete
    if state.briefing:
        import json
        arxiv_id = state.briefing.arxiv_id or state.arxiv_id or ""
        briefing_dict = _build_briefing_dict(state)
        print(f"[EVENT SENT] complete: arxiv_id={arxiv_id}", flush=True)
        yield {
            "data": json.dumps({
                "type": "complete",
                "arxiv_id": arxiv_id,
                "briefing": briefing_dict,
            })
        }
    else:
        # Graph ran but produced no briefing — surface error
        error_msg = "; ".join(state.errors) if state.errors else "Pipeline completed without output"
        print(f"[EVENT SENT] error: {error_msg[:200]}", flush=True)
        yield {"data": f'{{"type":"error","message":"{error_msg[:200]}"}}'}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/api/digest")
async def digest(request: DigestRequest):
    """Run Graph A and stream SSE progress events."""
    print(f"[UI REQUEST] query=\"{request.query}\"", flush=True)
    return EventSourceResponse(_digest_event_generator(request.query))


@app.get("/api/briefing/{arxiv_id}")
async def get_briefing(arxiv_id: str):
    """Return the completed briefing for a saved session."""
    try:
        state = load_session(arxiv_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {arxiv_id}")

    if not state.briefing:
        raise HTTPException(status_code=404, detail="Briefing not yet generated for this session")

    return _build_briefing_dict(state)


@app.post("/api/qa/{arxiv_id}")
async def qa(arxiv_id: str, request: QARequest):
    """Answer one question grounded in the paper's indexed chunks."""
    try:
        state = load_session(arxiv_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {arxiv_id}")

    loop = asyncio.get_event_loop()
    question = request.question.strip()

    def _run_qa():
        _, turn = answer_question(state, question)
        return turn

    try:
        turn = await loop.run_in_executor(None, _run_qa)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return _build_qa_turn_dict(turn, question)


@app.get("/api/sessions")
async def sessions():
    """List all saved sessions."""
    return list_sessions()


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
