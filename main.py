"""Autonomous arXiv Paper Digest & QA Agent — Main CLI Entry Point.

Commands:
  digest  : Run Graph A — Query Understanding → Retrieval → Selection → PDF Parse → Chunk & Embed → Briefing
  ask     : Run Graph B — Grounded QA loop over hydrated session without re-parsing
  session : Inspect or list saved sessions on disk
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from config import CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_MODEL
from src.graph import build_digest_graph
from src.nodes.qa import answer_question
from src.state import AgentState
from src.utils.errors import SessionNotFoundError
from src.utils.logging import display_banner, display_candidates_table, log_error, log_info, log_warning
from src.utils.session import list_sessions, load_session, save_session

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = typer.Typer(
    name="arxiv-digest",
    help="Autonomous arXiv Paper Digest & QA Agent — Free Tier / Fully Local",
    add_completion=False,
)
console = Console()


@app.command(name="digest")
def digest_cmd(
    query: str = typer.Argument(..., help="Research topic, arXiv ID (e.g. 2401.12345), or arXiv URL"),
    max_results: int = typer.Option(5, "--max-results", "-n", help="Maximum candidates to retrieve for topic search"),
) -> None:
    """Ingest a query, retrieve papers, parse PDF, index embeddings, and generate an executive briefing."""
    display_banner(
        f"[bold white]Autonomous arXiv Paper Digest & QA Agent[/bold white]\n"
        f"[cyan]Input Query:[/cyan] {query}",
        style="bold white on navy_blue",
    )

    initial_state = AgentState(raw_input=query.strip())
    graph = build_digest_graph()

    try:
        raw_output = graph.invoke(initial_state)
        state = AgentState.model_validate(raw_output)
    except Exception as exc:
        log_error(f"Execution failed during graph execution: {exc}")
        raise typer.Exit(code=1)

    # Display Node Execution Trace
    trace_str = " -> ".join(f"[bold cyan]{node}[/bold cyan]" for node in state.node_trace)
    console.print(Panel(f"[dim]Execution Route:[/dim] {trace_str}", title="LangGraph Node Trace", border_style="cyan"))

    # Check for Clarification branch (zero results)
    if "clarify" in state.node_trace:
        log_warning("No matching arXiv papers found for your search query.")
        console.print("\n[bold yellow]Suggestions to refine your search:[/bold yellow]")
        for s in state.clarification_suggestions:
            console.print(f"  - {s}")
        raise typer.Exit(code=0)

    # Display Candidates Table if Topic Search was performed
    if state.intent == "topic_search" and state.candidates:
        display_candidates_table(state.candidates)
        if state.selected_paper:
            console.print(
                f"[bold green][OK] Selected Paper:[/bold green] [{state.selected_paper.arxiv_id}] {state.selected_paper.title}"
            )
            if state.selection_reason:
                console.print(f"[dim]Selection Rationale:[/dim] {state.selection_reason}\n")

    # Display Executive Briefing
    if state.briefing:
        console.print(Panel(Markdown(state.briefing.to_markdown()), title="Executive Briefing", border_style="green"))
        arxiv_id = state.selected_paper.arxiv_id if state.selected_paper else state.arxiv_id
        console.print(
            f"\n[bold green][OK] Pipeline complete![/bold green] Session saved to disk."
            f"\nYou can ask follow-up questions using:\n  [bold cyan]python main.py ask {arxiv_id}[/bold cyan]\n"
        )
    else:
        log_warning("No briefing was generated.")
        if state.errors:
            for err in state.errors:
                log_error(err)


@app.command(name="ask")
def ask_cmd(
    arxiv_id: str = typer.Argument(..., help="arXiv ID of the ingested paper (e.g. 1706.03762)"),
    question: Optional[str] = typer.Argument(None, help="Optional single question to ask. If omitted, starts interactive QA."),
) -> None:
    """Ask grounded questions against an ingested paper's indexed chunks (Graph B)."""
    try:
        state = load_session(arxiv_id)
    except SessionNotFoundError:
        log_error(
            f"Session for arXiv ID '{arxiv_id}' not found. "
            f"Please run 'python main.py digest {arxiv_id}' first."
        )
        raise typer.Exit(code=1)

    paper_title = state.selected_paper.title if state.selected_paper else "Academic Paper"
    display_banner(
        f"[bold white]Grounded Q&A: {paper_title}[/bold white]\n"
        f"[dim]arXiv ID: {arxiv_id} | Chunks: {state.n_chunks}[/dim]",
        style="bold white on dark_green",
    )

    if question:
        # Single question execution
        state, turn = answer_question(state, question)
        _display_qa_turn(turn)
        return

    # Interactive QA Loop
    console.print("[dim]Type your question below, or 'exit' / 'quit' to end the session.[/dim]\n")
    while True:
        try:
            user_q = Prompt.ask("[bold cyan]Question[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            break

        if not user_q or user_q.strip().lower() in {"exit", "quit", "q"}:
            console.print("\n[dim]Exiting QA session. Goodbye![/dim]")
            break

        state, turn = answer_question(state, user_q)
        _display_qa_turn(turn)


def _display_qa_turn(turn) -> None:
    """Render a QA turn with answer, grounding indicator, and chunk citations."""
    status_tag = "[bold red]Refusal (Out of paper scope)[/bold red]" if turn.is_refusal else "[bold green]Grounded Answer[/bold green]"
    content = f"**Status:** {status_tag}\n\n{turn.answer}"
    if turn.chunk_ids:
        citations_str = " ".join(f"`{c}`" for c in turn.chunk_ids)
        content += f"\n\n**Cited Chunks:** {citations_str}"

    console.print(Panel(Markdown(content), title=f"Q: {turn.question}", border_style="cyan"))
    console.print()


@app.command(name="session")
def session_cmd(
    arxiv_id: Optional[str] = typer.Argument(None, help="arXiv ID to inspect. If omitted, lists all saved sessions."),
) -> None:
    """Inspect or list saved paper sessions on disk."""
    if not arxiv_id:
        sessions = list_sessions()
        if not sessions:
            console.print("[yellow]No saved sessions found in data/sessions/.[/yellow]")
            return

        table = Table(title="Saved Paper Sessions", show_lines=True)
        table.add_column("arXiv ID", style="cyan", width=16)
        table.add_column("Title", style="bold white")
        table.add_column("Chunks", justify="right", width=8)
        table.add_column("QA Turns", justify="right", width=10)
        table.add_column("Briefing", justify="center", width=10)

        for s in sessions:
            table.add_row(
                s["arxiv_id"],
                s["title"][:50] + ("..." if len(s["title"]) > 50 else ""),
                str(s["n_chunks"]),
                str(s["qa_turns"]),
                "[green]✔[/green]" if s["has_briefing"] else "[red]✖[/red]",
            )
        console.print(table)
        return

    try:
        state = load_session(arxiv_id)
    except SessionNotFoundError:
        log_error(f"No saved session found for '{arxiv_id}'.")
        raise typer.Exit(code=1)

    console.print(Panel(
        f"[bold cyan]arXiv ID:[/bold cyan] {state.arxiv_id or (state.selected_paper.arxiv_id if state.selected_paper else 'N/A')}\n"
        f"[bold cyan]Title:[/bold cyan] {state.selected_paper.title if state.selected_paper else 'N/A'}\n"
        f"[bold cyan]Indexed Chunks:[/bold cyan] {state.n_chunks}\n"
        f"[bold cyan]Parse Method:[/bold cyan] {state.parse_method} (Degraded: {state.parse_degraded})\n"
        f"[bold cyan]QA History:[/bold cyan] {len(state.qa_history)} turn(s)\n"
        f"[bold cyan]Briefing Generated:[/bold cyan] {state.briefing is not None}",
        title=f"Session Details: {arxiv_id}",
        border_style="cyan",
    ))


@app.command(name="diagnose")
def diagnose_cmd() -> None:
    """Run full 10-point system diagnostic test covering all services and APIs."""
    from src.utils.diagnostic import run_diagnostics
    success = run_diagnostics()
    raise typer.Exit(code=0 if success else 1)


if __name__ == "__main__":
    if "--diagnose" in sys.argv:
        from src.utils.diagnostic import run_diagnostics
        success = run_diagnostics()
        sys.exit(0 if success else 1)
    app()
