"""Rich console singleton and display helpers for the MIND CLI."""

import logging

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

console = Console()


def install_rich_logging(level: str = "INFO") -> None:
    """Replace the root logger's console handler with a RichHandler."""
    root = logging.getLogger()
    # Remove existing StreamHandlers to avoid duplicate output
    root.handlers = [
        h for h in root.handlers if not isinstance(h, logging.StreamHandler)
    ]
    rich_handler = RichHandler(
        console=console,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    rich_handler.setLevel(level)
    root.addHandler(rich_handler)


def print_config_panel(title: str, rows: list[tuple[str, str]]) -> None:
    """Display a Rich table panel summarising the run configuration.

    Parameters
    ----------
    title : str
        Panel heading.
    rows : list[tuple[str, str]]
        (label, value) pairs to display.
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", min_width=20)
    table.add_column()
    for label, value in rows:
        table.add_row(label, str(value))
    console.print(Panel(table, title=f"[bold]{title}[/bold]", expand=False))


def success(msg: str) -> None:
    console.print(f"[bold green]OK[/bold green] {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]ERROR[/bold red] {msg}")
