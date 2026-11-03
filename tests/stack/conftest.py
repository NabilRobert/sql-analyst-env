"""Fixtures for tests that need the local stack (docker compose up -d --wait)."""

import asyncio
from pathlib import Path

import pytest

from analyst_env.backbone import mcp_url, read_stack_keys
from analyst_env.task_checks import CheckFailure, check_tasks
from analyst_env.tasks import Task, load_task_file

PUBLIC_TASKS = Path(__file__).resolve().parents[2] / "tasks" / "public.yaml"


def public_tasks() -> list[Task]:
    return load_task_file(PUBLIC_TASKS).tasks


@pytest.fixture(scope="session")
def stack_keys() -> dict[str, str]:
    return read_stack_keys()


@pytest.fixture(scope="session")
def public_task_failures(stack_keys: dict[str, str]) -> dict[str, list[CheckFailure]]:
    """Every public task checked once, in one pass over the stack."""
    return asyncio.run(check_tasks(public_tasks(), mcp_url(), stack_keys))
