"""Command line: `uv run analyst-env --help`."""

import asyncio

import typer

from analyst_env.backbone import mcp_url, open_copies, read_stack_keys
from analyst_env.fingerprint import fingerprint, load_stored_fingerprints, write_fingerprints

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Tools for the local stack and its tasks."""


async def _live_fingerprints() -> dict[str, str]:
    async with open_copies(mcp_url(), read_stack_keys()) as copies:
        return {copy.name: await fingerprint(copy) for copy in copies}


@app.command("fingerprint")
def fingerprint_command(
    write: bool = typer.Option(
        False, help="Store the live fingerprints in stack/fingerprints.json"
    ),
) -> None:
    """Compare each data copy's fingerprint with the stored one, or store it."""
    live = asyncio.run(_live_fingerprints())
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
