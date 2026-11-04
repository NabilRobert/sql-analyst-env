"""Command line: `uv run analyst-env --help`."""

import asyncio

import typer

from analyst_env.baselines import find_model, run_baseline
from analyst_env.fingerprint import live_fingerprints, load_stored_fingerprints, write_fingerprints
from analyst_env.results import write_results
from analyst_env.run_record import write_record
from analyst_env.tasks import Split

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Tools for the local stack and its tasks."""


@app.command("fingerprint")
def fingerprint_command(
    write: bool = typer.Option(
        False, help="Store the live fingerprints in stack/fingerprints.json"
    ),
) -> None:
    """Compare each data copy's fingerprint with the stored one, or store it."""
    live = asyncio.run(live_fingerprints())
    if write:
        write_fingerprints(live)
        typer.echo("stored: " + ", ".join(f"{name} {digest[:12]}" for name, digest in live.items()))
        return
    stored = load_stored_fingerprints()
    for name, digest in live.items():
        status = "ok" if stored.get(name) == digest else "DIFFERENT"
        typer.echo(f"{name}: {digest[:12]} {status}")
    if live != stored:
        raise typer.Exit(code=1)


@app.command("baseline")
def baseline_command(model: str, split: Split) -> None:
    """Run one baseline, five tries per task, and write its run record. MODEL is
    an Ollama tag from analyst_env/baselines.py; SPLIT is dev, or heldout
    (with ANALYST_ENV_HELDOUT_FILE set)."""
    path = write_record(run_baseline(find_model(model), split))
    typer.echo(f"record: {path}")


@app.command("results")
def results_command() -> None:
    """Regenerate RESULTS.md from the run records."""
    write_results()
