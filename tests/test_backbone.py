"""The client refuses any MCP-backbone that isn't on this machine (E4)."""

import asyncio

import pytest

from analyst_env.backbone import (
    DEFAULT_MCP_URL,
    BackboneUnreachable,
    NotLocalError,
    connect,
    ensure_local,
    mcp_url,
)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8766/mcp/", "http://localhost:1/mcp/"])
def test_local_addresses_are_allowed(url: str) -> None:
    ensure_local(url)


@pytest.mark.parametrize(
    "url",
    ["https://example.com/mcp/", "http://10.0.0.5:8000/mcp/", "http://127.0.0.1.example.com/mcp/"],
)
def test_other_addresses_are_refused(url: str) -> None:
    with pytest.raises(NotLocalError, match="must be local"):
        ensure_local(url)


def test_the_url_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANALYST_ENV_MCP_URL", raising=False)
    assert mcp_url() == DEFAULT_MCP_URL
    monkeypatch.setenv("ANALYST_ENV_MCP_URL", "http://127.0.0.1:9/mcp/")
    assert mcp_url() == "http://127.0.0.1:9/mcp/"


def test_an_unreachable_backbone_says_how_to_start_it() -> None:
    async def connect_to_nothing() -> None:
        async with connect("copy_a", "http://127.0.0.1:1/mcp/", "unused-key"):
            pass

    with pytest.raises(BackboneUnreachable, match="docker compose up"):
        asyncio.run(connect_to_nothing())
