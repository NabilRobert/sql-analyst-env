"""A small client for the local MCP-backbone: runs one query on one data
copy and returns what the server said.

The connection code follows agent-eval-harness's agent_eval/mcp_client.py
(commit a44cad4): the key goes in the Authorization header, never in a
tool argument a model could see (requirement E2)."""

import json
import os
import subprocess
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client  # pyright: ignore[reportPrivateUsage]
from pydantic import BaseModel

from analyst_env.grading import Row

REPO_ROOT = Path(__file__).resolve().parents[1]
# compose.yaml publishes MCP-backbone here, on localhost only.
DEFAULT_MCP_URL = "http://127.0.0.1:8766/mcp/"
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
COPY_NAMES = ("copy_a", "copy_b")


class NotLocalError(ValueError):
    """Raised for an MCP-backbone address that isn't on this machine."""


class BackboneUnreachable(RuntimeError):
    """Raised when nothing answers at the MCP-backbone address."""


class QueryResult(BaseModel):
    """What run_query returned: `status` is succeeded, rejected, errored
    or timed_out; `error` says why for anything but success."""

    status: str
    rows: list[Row] = []
    error: str | None = None
    truncated: bool = False

    @property
    def is_success(self) -> bool:
        return self.status == "succeeded"


def mcp_url() -> str:
    return os.environ.get("ANALYST_ENV_MCP_URL", DEFAULT_MCP_URL)


def ensure_local(url: str) -> None:
    """Refuses anything but this machine (requirement E4): the live server
    has a 5-queries-an-hour limit and isn't for training runs."""
    host = urlsplit(url).hostname
    if host not in LOCAL_HOSTS:
        raise NotLocalError(
            f"MCP-backbone must be local, got host {host!r}: "
            "start the stack with `docker compose up -d --wait`"
        )


def read_stack_keys() -> dict[str, str]:
    """Each copy's workspace key, from the stack's `out` volume. Read with
    `docker compose exec` so no key file lands on the host."""
    command = ["docker", "compose", "-f", str(REPO_ROOT / "compose.yaml")]
    command += ["exec", "-T", "mcp", "cat", "/out/keys.json"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "can't read the stack's keys: is it running? "
            f"Start it with `docker compose up -d --wait`. ({completed.stderr.strip()})"
        )
    return cast(dict[str, str], json.loads(completed.stdout))


class BackboneCopy:
    """One open MCP session on one data copy's workspace."""

    def __init__(self, name: str, session: ClientSession) -> None:
        self.name = name
        self._session = session

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Any MCP-backbone tool's answer, as JSON data. A refused call
        (unknown table, bad key) comes back as {"error": reason}."""
        result = await self._session.call_tool(name, arguments)
        first = result.content[0] if result.content else None
        text = str(getattr(first, "text", ""))
        if result.is_error:
            return {"error": text}
        data: Any = result.structured_content or json.loads(text)
        # FastMCP wraps a non-object return value as {"result": ...}.
        if isinstance(data, dict) and set(cast(dict[str, Any], data)) == {"result"}:
            return cast(dict[str, Any], data)["result"]
        return cast(Any, data)

    async def run_query(self, sql: str) -> QueryResult:
        return QueryResult.model_validate(await self.call_tool("run_query", {"sql": sql}))


@asynccontextmanager
async def connect(name: str, url: str, api_key: str) -> AsyncGenerator[BackboneCopy]:
    ensure_local(url)
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {api_key}"})
    try:
        async with (
            http,
            streamable_http_client(url, http_client=http) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            yield BackboneCopy(name, session)
    except ExceptionGroup as group:
        # The MCP client runs in a task group, so a refused connection
        # arrives wrapped; unwrap it into something a person can act on.
        if group.subgroup(httpx2.ConnectError) is None:
            raise
        raise BackboneUnreachable(
            f"nothing answers at {url}: start the stack with `docker compose up -d --wait`, "
            "or check ANALYST_ENV_MCP_URL"
        ) from group


@asynccontextmanager
async def open_copies(url: str, keys: dict[str, str]) -> AsyncGenerator[list[BackboneCopy]]:
    """A session on every data copy, in COPY_NAMES order."""
    async with AsyncExitStack() as stack:
        copies = [
            await stack.enter_async_context(connect(name, url, keys[name])) for name in COPY_NAMES
        ]
        yield copies
