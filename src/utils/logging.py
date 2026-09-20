"""Console logging and timing utilities powered by Rich.

Provides consistent node execution timing, formatted status banners,
and cross-platform safe terminal output (Windows/Linux/macOS).
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


@contextmanager
def timed_node(node_name: str, description: str = "") -> Iterator[None]:
    """Context manager for node-level timing and clear terminal feedback."""
    label = f"[bold cyan]Node: {node_name}[/bold cyan]"
    if description:
        label += f" — [dim]{description}[/dim]"
    console.print(f"> {label} ...")
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        console.print(f"  +-- [green][OK] Done[/green] in [yellow]{elapsed:.2f}s[/yellow]\n")


def log_error(msg: str) -> None:
    """Print formatted error message."""
    console.print(f"[bold red][ERROR][/bold red] {msg}")


def log_warning(msg: str) -> None:
    """Print formatted warning message."""
    console.print(f"[bold yellow][WARNING][/bold yellow] {msg}")


def log_info(msg: str) -> None:
    """Print informational message."""
    console.print(f"[dim][INFO][/dim] {msg}")


def display_candidates_table(candidates: list, title: str = "Retrieved arXiv Papers") -> None:
    """Render candidates list as a clean Rich table."""
    table = Table(title=title, show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("arXiv ID", style="cyan", width=16)
    table.add_column("Title", style="bold white")
    table.add_column("Published", style="green", width=12)

    for i, p in enumerate(candidates, 1):
        arxiv_id = getattr(p, "arxiv_id", "")
        p_title = getattr(p, "title", "")
        pub = str(getattr(p, "published", ""))[:10]
        table.add_row(str(i), arxiv_id, p_title, pub)

    console.print(table)


def display_banner(text: str, style: str = "bold white on blue") -> None:
    """Display a prominent header panel."""
    console.print(Panel(text, style=style, expand=False))


def log_stage(stage: str, ok: bool, reason: str = "") -> None:
    """Expose stage diagnostic information in development/execution mode."""
    tag = f"[{stage:<12}]"
    if ok:
        status = "[bold green]OK[/bold green]"
        extra = f" [dim]({reason})[/dim]" if reason else ""
        console.print(f"{tag} {status}{extra}")
    else:
        status = "[bold red]FAILED[/bold red]"
        extra = f"\n  [red]Reason: {reason}[/red]" if reason else ""
        console.print(f"{tag} {status}{extra}")
