"""The copies hold the data their stored fingerprints describe (D3)."""

import asyncio

import pytest

from analyst_env.backbone import mcp_url, open_copies
from analyst_env.fingerprint import (
    FingerprintError,
    live_fingerprints,
    load_stored_fingerprints,
    mismatched_copies,
)
from analyst_env.task_checks import check_tasks
from tests.stack.conftest import public_tasks

pytestmark = pytest.mark.stack


def test_live_fingerprints_match_the_stored_ones(stack_keys: dict[str, str]) -> None:
    assert asyncio.run(live_fingerprints()) == load_stored_fingerprints()


def test_the_copies_have_different_data(stack_keys: dict[str, str]) -> None:
    live = asyncio.run(live_fingerprints())
    assert live["copy_a"] != live["copy_b"]


def test_a_copy_with_other_data_is_named(stack_keys: dict[str, str]) -> None:
    async def mismatched() -> list[str]:
        stored = {**load_stored_fingerprints(), "copy_b": "0" * 64}
        async with open_copies(mcp_url(), stack_keys) as copies:
            return await mismatched_copies(copies, stored)

    assert asyncio.run(mismatched()) == ["copy_b"]


def test_checks_refuse_to_run_on_other_data(
    stack_keys: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "analyst_env.task_checks.load_stored_fingerprints", lambda: {"copy_a": "0", "copy_b": "0"}
    )
    with pytest.raises(FingerprintError, match="copy_a, copy_b: data doesn't match"):
        asyncio.run(check_tasks(public_tasks()[:1], mcp_url(), stack_keys))
