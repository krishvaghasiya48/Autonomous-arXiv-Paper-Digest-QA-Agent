"""Session management — save and hydrate AgentState on disk.

Permits Graph B (QA loop) to resume instantly from a serialized session
file without repeating query parsing, paper retrieval, PDF extraction,
or embedding upserts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import SESSION_DIR
from src.state import AgentState
from src.utils.errors import SessionNotFoundError


def _safe_session_filename(arxiv_id: str) -> str:
    """Normalize arxiv ID into a safe file basename."""
    safe = arxiv_id.replace("/", "_").replace(":", "_").strip()
    return f"{safe}.json"


def session_path_for(arxiv_id: str) -> Path:
    """Return the absolute Path to the session json file for a given arxiv ID."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR / _safe_session_filename(arxiv_id)


def save_session(state: AgentState) -> Path:
    """Serialize the full AgentState to data/sessions/<safe_arxiv_id>.json.

    Returns the path where the session was saved.
    """
    arxiv_id = state.arxiv_id
    if not arxiv_id and state.selected_paper:
        arxiv_id = state.selected_paper.arxiv_id

    if not arxiv_id:
        arxiv_id = "anonymous_session"

    path = session_path_for(arxiv_id)
    data = state.model_dump(mode="json")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_session(arxiv_id: str) -> AgentState:
    """Load and hydrate an AgentState from disk.

    Raises SessionNotFoundError if the file does not exist.
    """
    path = session_path_for(arxiv_id)
    if not path.exists():
        raise SessionNotFoundError(arxiv_id)

    raw_text = path.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    return AgentState.model_validate(data)


def list_sessions() -> list[dict[str, Any]]:
    """List all saved sessions found in data/sessions/."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for f in sorted(SESSION_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append({
                "arxiv_id": data.get("arxiv_id") or (data.get("selected_paper") or {}).get("arxiv_id", f.stem),
                "title": (data.get("selected_paper") or {}).get("title", "Unknown Title"),
                "file": str(f),
                "n_chunks": data.get("n_chunks", 0),
                "qa_turns": len(data.get("qa_history", [])),
                "has_briefing": data.get("briefing") is not None,
            })
        except Exception:
            continue
    return results
