"""The public task file's shape (ADR-007). The answer keys themselves are
checked against the stack in tests/stack/."""

from collections import Counter

import pytest
from pydantic import ValidationError

from analyst_env.tasks import HELDOUT_ONLY_FAMILIES, PUBLIC_TASKS, TaskFile, load_task_file

EXPECTED_REUSED_TASKS = 40  # MCP-backbone's 30 plus agent-eval-harness's 10
# ADR-007: train 60 (the 40 reused and 20 new) and dev 10, all public.
EXPECTED_PUBLIC_SPLITS = {"train": 60, "dev": 10}
EXPECTED_TEMPTING_TASKS = 3  # of 5; the other 2 are held out


def test_public_file_holds_the_reused_tasks() -> None:
    tasks = load_task_file(PUBLIC_TASKS).tasks
    reused = [task for task in tasks if task.source != "new"]
    assert len(reused) == EXPECTED_REUSED_TASKS


def test_public_file_holds_no_held_out_task() -> None:
    assert all(task.split != "heldout" for task in load_task_file(PUBLIC_TASKS).tasks)


def test_public_file_holds_train_60_and_dev_10() -> None:
    splits = Counter(task.split for task in load_task_file(PUBLIC_TASKS).tasks)
    assert splits == EXPECTED_PUBLIC_SPLITS


def test_reused_tasks_are_all_train() -> None:
    tasks = load_task_file(PUBLIC_TASKS).tasks
    assert {task.split for task in tasks if task.source != "new"} == {"train"}


def test_held_out_only_families_are_absent_from_the_public_file() -> None:
    families = {task.family for task in load_task_file(PUBLIC_TASKS).tasks}
    assert families.isdisjoint(HELDOUT_ONLY_FAMILIES)


def test_public_file_holds_the_public_tempting_tasks() -> None:
    tasks = load_task_file(PUBLIC_TASKS).tasks
    assert sum(task.family == "tempting" for task in tasks) == EXPECTED_TEMPTING_TASKS


def test_public_file_carries_the_canary() -> None:
    assert load_task_file(PUBLIC_TASKS).canary in PUBLIC_TASKS.read_text(encoding="utf-8")


def _file_with(tasks: list[dict[str, object]]) -> dict[str, object]:
    return {"suite": "s", "version": 1, "description": "d", "canary": "c", "tasks": tasks}


def _task(task_id: str, tags: list[str]) -> dict[str, object]:
    return {
        "id": task_id,
        "tags": tags,
        "family": "counting",
        "split": "train",
        "source": "new",
        "prompt": "p",
        "reference_sql": "select 1",
        "alternative_sql": "select 1",
        "wrong_sql": "select 2",
    }


def test_duplicate_ids_are_refused() -> None:
    with pytest.raises(ValidationError, match="duplicate task ids"):
        TaskFile.model_validate(_file_with([_task("a", ["easy"]), _task("a", ["easy"])]))


def test_a_task_needs_exactly_one_difficulty() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        TaskFile.model_validate(_file_with([_task("a", ["easy", "hard"])]))


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        TaskFile.model_validate(_file_with([{**_task("a", ["easy"]), "answer": "42"}]))
