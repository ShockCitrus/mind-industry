"""Root Typer application for the MIND CLI.

Entry point: ``mind`` (registered via ``[project.scripts]`` in pyproject.toml).
"""

import typer

from mind.cli.commands import data, detect, tm

app = typer.Typer(
    name="mind",
    help="MIND — Multilingual INconsistency Detection CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(detect.app, name="detect", help="Discrepancy detection commands.")
app.add_typer(data.app, name="data", help="Data preprocessing commands.")
app.add_typer(tm.app, name="tm", help="Topic modeling commands.")


if __name__ == "__main__":
    app()
