"""Command-line interface. Track 0 ships the command surface; Track B fills it in.

Commands: query, rank, replay, diff, eval, export, serve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="materials-triage: triage candidate materials from public data.",
)

NOT_IMPLEMENTED = "not implemented (Track B)"


@app.command()
def query(
    request: Annotated[str, typer.Argument(help="Natural-language request from the PI")],
    profile: Annotated[
        str, typer.Option(help="Scoring profile name")
    ] = "oxide_dielectric_thin_film",
    yes: Annotated[
        bool, typer.Option("--yes", help="Skip the parsed-criteria confirmation")
    ] = False,
    no_llm: Annotated[
        bool,
        typer.Option(
            "--no-llm", help="Parse from --criteria, skip classification, template rationale"
        ),
    ] = False,
    criteria: Annotated[Path | None, typer.Option(help="Criteria file for --no-llm mode")] = None,
    view: Annotated[str, typer.Option(help="pi_summary | audit")] = "pi_summary",
) -> None:
    """Parse a request, confirm criteria, run the pipeline, render a view."""
    typer.echo(NOT_IMPLEMENTED)
    raise typer.Exit(code=2)


@app.command()
def rank(
    formulas: Annotated[list[str], typer.Option("--formulas", help="Candidate formulas or MP ids")],
    profile: Annotated[str, typer.Option()] = "oxide_dielectric_thin_film",
) -> None:
    """Rank a PI-supplied candidate list on the same criteria as discovery."""
    typer.echo(NOT_IMPLEMENTED)
    raise typer.Exit(code=2)


@app.command()
def replay(run_id: Annotated[str, typer.Argument(help="Run id of a stored bundle")]) -> None:
    """Re-rank a stored bundle with no fetching."""
    typer.echo(NOT_IMPLEMENTED)
    raise typer.Exit(code=2)


@app.command()
def diff(run_a: str, run_b: str) -> None:
    """Attribute rank changes between two runs to data, config, or model."""
    typer.echo(NOT_IMPLEMENTED)
    raise typer.Exit(code=2)


@app.command()
def eval(  # noqa: A001 - command name from the plan
    suite: Annotated[str, typer.Option(help="Eval suite or case id")] = "all",
) -> None:
    """Run the eval suite (Track E runner)."""
    typer.echo(NOT_IMPLEMENTED)
    raise typer.Exit(code=2)


@app.command()
def export(
    run_id: str,
    fmt: Annotated[str, typer.Option("--format", help="json | csv | markdown")] = "json",
) -> None:
    """Export a stored bundle."""
    typer.echo(NOT_IMPLEMENTED)
    raise typer.Exit(code=2)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the API server (Track C)."""
    typer.echo(NOT_IMPLEMENTED)
    raise typer.Exit(code=2)


def main() -> None:
    app()
