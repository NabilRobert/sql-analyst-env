"""Fixtures for tests that need the local stack (docker compose up -d --wait).

They run on the public tasks, plus the held-out ones when
ANALYST_ENV_HELDOUT_FILE points at their file (Arthur's machine, not CI)."""

import asyncio

import pytest

from analyst_env.backbone import mcp_url, read_stack_keys
from analyst_env.task_checks import CheckFailure, check_tasks
from analyst_env.tasks import PUBLIC_TASKS, Task, load_all_tasks, load_task_file


def public_tasks() -> list[Task]:
    return load_task_file(PUBLIC_TASKS).tasks


def all_tasks() -> list[Task]:
    return load_all_tasks()


@pytest.fixture(scope="session")
def stack_keys() -> dict[str, str]:
    return read_stack_keys()


@pytest.fixture(scope="session")
def task_failures(stack_keys: dict[str, str]) -> dict[str, list[CheckFailure]]:
    """Every task checked once, in one pass over the stack."""
    return asyncio.run(check_tasks(all_tasks(), mcp_url(), stack_keys))
