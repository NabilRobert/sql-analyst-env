"""Every task passes all seven answer-key checks, and each check catches
the fault it exists for."""

import asyncio

import pytest

from analyst_env.backbone import mcp_url, open_copies
from analyst_env.task_checks import CheckFailure, check_task
from analyst_env.tasks import Task
from tests.stack.conftest import all_tasks

pytestmark = pytest.mark.stack

TASKS = all_tasks()


@pytest.mark.parametrize("task", TASKS, ids=[task.id for task in TASKS])
def test_task_passes_every_check(task: Task, task_failures: dict[str, list[CheckFailure]]) -> None:
    failures = task_failures[task.id]
    assert not failures, "\n".join(str(failure) for failure in failures)


def _checks_failed(stack_keys: dict[str, str], **changes: str) -> set[str]:
    """Which checks a copy of task e01 fails once `changes` are applied.
    Skips the fingerprint step, which test_fingerprints.py covers."""
    task = TASKS[0].model_copy(update=changes)

    async def run() -> list[CheckFailure]:
        async with open_copies(mcp_url(), stack_keys) as copies:
            return await check_task(task, copies)

    return {failure.check for failure in asyncio.run(run())}


def test_a_write_as_gold_fails_c1(stack_keys: dict[str, str]) -> None:
    assert _checks_failed(stack_keys, reference_sql="delete from film") == {"C1"}


def test_a_random_answer_fails_c2(stack_keys: dict[str, str]) -> None:
    random_film = "select film_id from film order by random() limit 1"
    assert "C2" in _checks_failed(stack_keys, reference_sql=random_film)


def test_a_tie_at_the_cut_fails_c3(stack_keys: dict[str, str]) -> None:
    # Hundreds of films share the longest rental_duration, so LIMIT 1 is luck.
    tied = "select title from film order by rental_duration desc limit 1"
    assert "C3" in _checks_failed(stack_keys, reference_sql=tied)


def test_an_empty_answer_fails_c4(stack_keys: dict[str, str]) -> None:
    empty = "select film_id from film where film_id < 0"
    assert _checks_failed(stack_keys, reference_sql=empty) == {"C4"}


def test_an_answer_over_the_row_cap_fails_c4(stack_keys: dict[str, str]) -> None:
    assert _checks_failed(stack_keys, reference_sql="select rental_id from rental") == {"C4"}


def test_a_constant_answer_fails_c5(stack_keys: dict[str, str]) -> None:
    constant = "select 955 as films"
    assert "C5" in _checks_failed(stack_keys, reference_sql=constant, alternative_sql=constant)


def test_a_disagreeing_alternative_fails_c6(stack_keys: dict[str, str]) -> None:
    disagreeing = _checks_failed(stack_keys, alternative_sql="select count(*) from inventory")
    assert disagreeing == {"C6"}


def test_a_wrong_reading_that_matches_fails_c7(stack_keys: dict[str, str]) -> None:
    assert _checks_failed(stack_keys, wrong_sql="select count(*) from film") == {"C7"}


def test_a_wrong_reading_that_does_not_run_fails_c7(stack_keys: dict[str, str]) -> None:
    assert _checks_failed(stack_keys, wrong_sql="delete from film") == {"C7"}
