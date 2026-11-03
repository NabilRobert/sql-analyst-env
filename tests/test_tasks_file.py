"""The public task file's shape. The answer keys themselves are checked
against the stack in tests/stack/."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from analyst_env.tasks import TaskFile, load_task_file

PUBLIC_TASKS = Path(__file__).resolve().parents[1] / "tasks" / "public.yaml"
EXPECTED_REUSED_TASKS = 40  # MCP-backbone's 30 plus agent-eval-harness's 10


def test_public_file_holds_the_reused_tasks() -> None:
    tasks = load_task_file(PUBLIC_TASKS).tasks
    reused = [task for task in tasks if task.source != "new"]
    assert len(reused) == EXPECTED_REUSED_TASKS


def test_public_file_holds_no_held_out_task() -> None:
    assert all(task.split != "heldout" for task in load_task_file(PUBLIC_TASKS).tasks)


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
