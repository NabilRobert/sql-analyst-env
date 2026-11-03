# This file runs inside the MCP-backbone image, where `app` and `scripts`
# are importable; on the host they aren't, so pyright can't see their types.
# pyright: reportMissingImports=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
"""One-shot setup for the local stack (runs inside the MCP-backbone image).

Adapted from agent-eval-harness's repro/setup_repro.py (commit a44cad4):
the same steps, each done with MCP-backbone's own scripts, plus two
perturbed copies of Pagila (ADR-009) and one workspace per copy.

1. Load Pagila at a pinned upstream commit into `pagila` (the template).
2. Make `copy_a` (what the agent sees) and `copy_b` (grading only) from it
   with make_copies.sql, each from its own seed.
3. Give each copy its own read-only role.
4. Migrate MCP-backbone's bookkeeping database.
5. Seed one workspace per copy, with raised limits, and write their keys
   to /out/keys.json.

Runs once; a second run is a no-op, and a run that stopped halfway
starts over. Writes /out/mcp.env for serve.sh.
"""

import asyncio
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

ADMIN = "postgresql://postgres:local-only@db:5432"
OUT = Path("/out")
DONE = OUT / ".setup-done"
COPY_SCRIPT = "/stack/make_copies.sql"

# Each copy differs from the other in every way the tasks can see: which
# rows are deleted (seed) and how many, how lengths and payments shift, and
# how many rows are added. Different counts make counting questions differ.
COPIES: dict[str, dict[str, str]] = {
    "copy_a": {
        "seed": "copy-a-2026",
        "film_drop_per_256": "13",
        "length_offset": "1",
        "payment_scale": "1.03",
        "new_countries": "1",
        "new_actors": "2",
        "new_canada_cities": "1",
    },
    "copy_b": {
        "seed": "copy-b-2026",
        "film_drop_per_256": "20",
        "length_offset": "-1",
        "payment_scale": "1.06",
        "new_countries": "2",
        "new_actors": "1",
        "new_canada_cities": "2",
    },
}

# Far above what a full task-check run or a baseline uses in an hour, but
# still a limit: a runaway loop gets stopped by MCP-backbone itself.
QUERIES_PER_HOUR = 100_000


def psql(*args: str, db: str = "postgres") -> None:
    subprocess.run(["psql", f"{ADMIN}/{db}", "-v", "ON_ERROR_STOP=1", "-q", *args], check=True)


def load_pagila(commit: str) -> None:
    import scripts.load_pagila_dataset as loader

    base = f"https://raw.githubusercontent.com/devrimgunduz/pagila/{commit}"
    loader.SCHEMA_URL = f"{base}/pagila-schema.sql"
    loader.DATA_URL = f"{base}/pagila-data.sql"
    loader.load("psql", f"{ADMIN}/pagila", Path("/tmp/pagila-cache"), scrub=False)


def make_copy(name: str, params: dict[str, str]) -> None:
    psql("-c", f"CREATE DATABASE {name} TEMPLATE pagila")
    variables = [arg for key, value in params.items() for arg in ("-v", f"{key}={value}")]
    psql(*variables, "-f", COPY_SCRIPT, db=name)
    psql("-c", "ANALYZE", db=name)


async def provision_roles() -> dict[str, str]:
    """A read-only role per copy, so a workspace's login can only reach
    its own copy. Returns each copy's connection URL."""
    from scripts.provision_readonly_role import provision

    urls: dict[str, str] = {}
    for name in COPIES:
        role = f"{name}_ro"
        password = await provision(f"{ADMIN}/{name}", role, name, "public")
        urls[name] = f"postgresql+asyncpg://{role}:{password}@db:5432/{name}"
    return urls


def write_server_settings(urls: dict[str, str]) -> dict[str, str]:
    from cryptography.fernet import Fernet

    settings = {
        "APP_DATABASE_URL": "postgresql+asyncpg://postgres:local-only@db:5432/bookkeeping",
        # Required by MCP-backbone; every workspace names its own copy anyway.
        "APP_TARGET_DATABASE_URL": urls["copy_a"],
        "APP_CONNECTION_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        # The copies are on the Compose network, a private address.
        "APP_ALLOW_PRIVATE_TARGETS": "true",
    }
    (OUT / "mcp.env").write_text("".join(f"{k}={v}\n" for k, v in settings.items()))
    return settings


async def seed_workspaces(urls: dict[str, str]) -> dict[str, str]:
    """Must run after the settings are in os.environ: MCP-backbone reads
    them once, when app.config is first imported."""
    from app.auth.workspaces import WorkspaceSpec
    from scripts.seed_workspace import seed

    keys: dict[str, str] = {}
    for name, url in urls.items():
        spec = WorkspaceSpec(
            name=name,
            console_username=name,
            console_password=secrets.token_urlsafe(16),
            created_via="operator",
            connection_url=url,
            query_rate_limit=QUERIES_PER_HOUR,
            sample_rate_limit=QUERIES_PER_HOUR,
        )
        keys[name] = await seed(spec)
    return keys


def main() -> int:
    if DONE.exists():
        print("already set up (`docker compose down -v` to start over)")
        return 0
    commit = os.environ["PAGILA_COMMIT"]
    OUT.mkdir(exist_ok=True)
    # No done-marker means no setup, or one that stopped halfway: start over.
    for database in ("bookkeeping", *COPIES, "pagila"):
        psql("-c", f"DROP DATABASE IF EXISTS {database} WITH (FORCE)")
    psql("-c", "CREATE DATABASE pagila")
    psql("-c", "CREATE DATABASE bookkeeping")

    print(f"== loading Pagila at upstream commit {commit}")
    load_pagila(commit)
    for name, params in COPIES.items():
        print(f"== making {name}")
        make_copy(name, params)

    print("== provisioning read-only roles")
    urls = asyncio.run(provision_roles())
    settings: dict[str, Any] = write_server_settings(urls)
    os.environ.update(settings)

    print("== migrating the bookkeeping database")
    subprocess.run(["alembic", "upgrade", "head"], cwd="/app", check=True)

    print("== seeding one workspace per copy")
    keys = asyncio.run(seed_workspaces(urls))
    (OUT / "keys.json").write_text(json.dumps(keys))
    DONE.write_text(f"pagila {commit}\n")
    print("== done: the server starts next")
    return 0


if __name__ == "__main__":
    sys.exit(main())
