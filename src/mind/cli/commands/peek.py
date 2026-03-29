"""``mind detect peek`` — inspect detection results."""

from pathlib import Path
from typing import Optional

import pandas as pd
import typer
import rich.box as box
from rich.panel import Panel
from rich.table import Table

from mind.cli._console import console, error

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LABEL_STYLES: dict[str, str] = {
    "CONTRADICTION":        "bold red",
    "CULTURAL_DISCREPANCY": "bold magenta",
    "NOT_ENOUGH_INFO":      "bold yellow",
    "NO_DISCREPANCY":       "bold green",
}
LABEL_ORDER: list[str] = list(LABEL_STYLES.keys())
PRIMARY_LABEL_COL = "final_label"



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_parquet(path: Path) -> Path:
    if path.is_dir():
        candidate = path / "mind_results.parquet"
        if not candidate.exists():
            error(f"No mind_results.parquet found in {path}")
            raise typer.Exit(1)
        return candidate
    if not path.exists():
        error(f"File not found: {path}")
        raise typer.Exit(1)
    return path


def _load_df(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)

    if PRIMARY_LABEL_COL not in df.columns or df[PRIMARY_LABEL_COL].isna().all():
        if "label" not in df.columns:
            error("Results file has neither 'final_label' nor 'label' column.")
            raise typer.Exit(1)
        df[PRIMARY_LABEL_COL] = df["label"]

    df[PRIMARY_LABEL_COL] = df[PRIMARY_LABEL_COL].replace("AGREEMENT", "NO_DISCREPANCY")

    if "topic" in df.columns:
        df["topic"] = pd.to_numeric(df["topic"], errors="coerce")

    return df


def _styled(label: str, text: str | None = None) -> str:
    style = LABEL_STYLES.get(label, "white")
    display = text if text is not None else label
    return f"[{style}]{display}[/{style}]"


def _truncate(text: str, max_chars: int = 300) -> str:
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + " [dim]…[/dim]"
    return text


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------

def _print_summary(df: pd.DataFrame) -> None:
    total = len(df)
    counts = df[PRIMARY_LABEL_COL].value_counts()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(min_width=26)
    table.add_column(justify="right", min_width=6)
    table.add_column(justify="right", min_width=7)
    table.add_column(min_width=22)

    table.add_row("[bold cyan]Total results[/bold cyan]", str(total), "", "")
    table.add_row("", "", "", "")

    for label in LABEL_ORDER:
        count = int(counts.get(label, 0))
        pct = (count / total * 100) if total > 0 else 0.0
        style = LABEL_STYLES[label]
        filled = int(pct / 5)
        bar = f"[{style}]{'█' * filled}[/{style}]{'░' * (20 - filled)}"
        table.add_row(
            f"[{style}]{label}[/{style}]",
            str(count),
            f"{pct:.1f}%",
            bar,
        )

    console.print(Panel(table, title="[bold]Results Summary[/bold]", expand=False))


def _print_topic_breakdown(df: pd.DataFrame) -> None:
    SHORT = {
        "CONTRADICTION":        "CONTRA",
        "CULTURAL_DISCREPANCY": "CULTURAL",
        "NOT_ENOUGH_INFO":      "NEI",
        "NO_DISCREPANCY":       "NO_DISC",
    }

    table = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
    table.add_column("Topic", style="bold cyan", justify="right", min_width=6)
    for label in LABEL_ORDER:
        style = LABEL_STYLES[label]
        table.add_column(f"[{style}]{SHORT[label]}[/{style}]", justify="right", min_width=9)
    table.add_column("Total", justify="right", min_width=6)

    grouped = (
        df.groupby("topic")[PRIMARY_LABEL_COL]
        .value_counts()
        .unstack(fill_value=0)
    )

    for topic_id in sorted(grouped.index):
        row_counts = grouped.loc[topic_id]
        row_total = int(row_counts.sum())
        cells = [str(int(topic_id)) if pd.notna(topic_id) else "?"]
        for label in LABEL_ORDER:
            count = int(row_counts.get(label, 0))
            style = LABEL_STYLES[label]
            cells.append(f"[{style}]{count}[/{style}]" if count > 0 else "0")
        cells.append(str(row_total))
        table.add_row(*cells)

    console.print(Panel(table, title="[bold]Per-Topic Breakdown[/bold]", expand=False))


def _print_result_card(
    row: "pd.Series",
    index: int,
    total: int,
    truncate_at: int = 300,
) -> None:
    label_val = str(row.get(PRIMARY_LABEL_COL, ""))
    style = LABEL_STYLES.get(label_val, "white")
    topic_val = row.get("topic", "?")
    if pd.notna(topic_val):
        topic_val = int(topic_val)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", min_width=22)
    table.add_column()

    def _row(label: str, value: str) -> None:
        table.add_row(label, value)

    _row("Topic",    str(topic_val))
    _row("Question", str(row.get("question", "")))
    table.add_row("", "")
    _row("Anchor passage",    _truncate(str(row.get("anchor_passage", "")), truncate_at))
    _row("Anchor answer",     str(row.get("anchor_answer", "")))
    table.add_row("", "")
    _row("Comparison passage", _truncate(str(row.get("comparison_passage", "")), truncate_at))
    _row("Comparison answer",  str(row.get("comparison_answer", "")))
    table.add_row("", "")
    _row("Label",  f"[{style}]{label_val}[/{style}]")
    _row("Reason", str(row.get("reason", "")))

    notes = row.get("Notes", "")
    if notes and str(notes).strip():
        _row("Notes", str(notes))

    sec = row.get("secondary_label", "")
    if sec and str(sec).strip():
        _row("Secondary label", str(sec))

    panel_title = (
        f"[bold]Result {index}/{total}[/bold]  "
        f"[{style}]{label_val}[/{style}]  "
        f"[dim]topic={topic_val}[/dim]"
    )
    console.print(Panel(table, title=panel_title, expand=False))


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

def peek(
    results: Path = typer.Argument(
        ...,
        help="Path to mind_results.parquet or a directory containing it.",
    ),
    topic: Optional[int] = typer.Option(
        None, "--topic", "-t",
        help="Filter result cards to a specific topic number.",
    ),
    label: Optional[str] = typer.Option(
        None, "--label", "-l",
        help=(
            "Filter result cards by label: CONTRADICTION, CULTURAL_DISCREPANCY, "
            "NOT_ENOUGH_INFO, NO_DISCREPANCY."
        ),
    ),
    limit: int = typer.Option(
        10, "--limit", "-n",
        help="Number of individual result cards to show (0 = all).",
        min=0,
    ),
    no_summary: bool = typer.Option(
        False, "--no-summary",
        help="Skip the results summary panel.",
    ),
    no_breakdown: bool = typer.Option(
        False, "--no-breakdown",
        help="Skip the per-topic breakdown table.",
    ),
    truncate: int = typer.Option(
        300, "--truncate",
        help="Max characters for passage display in cards (0 = no truncation).",
        min=0,
    ),
) -> None:
    """Inspect mind_results.parquet: summary, per-topic breakdown, and result cards."""
    parquet_path = _resolve_parquet(results)

    with console.status("[bold green]Loading results…"):
        df = _load_df(parquet_path)

    if df.empty:
        error("The results file is empty.")
        raise typer.Exit(1)

    # Validate and normalise label filter
    if label is not None:
        label = label.upper().replace("-", "_")
        label = label.replace("AGREEMENT", "NO_DISCREPANCY")
        if label not in LABEL_STYLES:
            valid = ", ".join(LABEL_STYLES.keys())
            error(f"Unknown label '{label}'. Valid values: {valid}")
            raise typer.Exit(1)

    # Summary and breakdown always use the full dataset
    if not no_summary:
        _print_summary(df)

    if not no_breakdown and "topic" in df.columns:
        _print_topic_breakdown(df)

    # Apply filters for individual cards
    filtered = df.copy()

    if topic is not None:
        filtered = filtered[filtered["topic"] == topic]
        if filtered.empty:
            error(f"No results found for topic {topic}.")
            raise typer.Exit(0)

    if label is not None:
        filtered = filtered[filtered[PRIMARY_LABEL_COL] == label]
        if filtered.empty:
            msg = f"No results with label '{label}'"
            msg += f" in topic {topic}." if topic is not None else "."
            error(msg)
            raise typer.Exit(0)

    display_slice = filtered if limit == 0 else filtered.head(limit)

    if len(display_slice) == 0:
        console.print("[yellow]No individual results to display.[/yellow]")
        raise typer.Exit(0)

    filter_parts = []
    if topic is not None:
        filter_parts.append(f"topic={topic}")
    if label is not None:
        filter_parts.append(f"label={label}")
    filter_str = f" [{', '.join(filter_parts)}]" if filter_parts else ""

    console.print(
        f"\n[bold]Showing {len(display_slice)} of {len(filtered)} results"
        f"{filter_str}[/bold]\n"
    )

    for i, (_, row) in enumerate(display_slice.iterrows(), start=1):
        _print_result_card(row, i, len(display_slice), truncate_at=truncate)
