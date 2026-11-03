"""The task files: one business question each, with its answer key.

The format is agent-eval-harness's suite YAML (`id`, `tags`, `prompt`,
`reference_sql`), so the harness can run these tasks unchanged (ADR-015),
plus the fields the answer-key checks need (ADR-008). Held-out tasks live
in tasks/private/, which git ignores (ADR-009)."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

Difficulty = Literal["easy", "medium", "hard", "expert"]
DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "medium", "hard", "expert")

Family = Literal[
    "counting",  # one table, a filter and a count
    "aggregates",  # sums, averages, extremes
    "joins",  # the answer needs two or more tables
    "grouping",  # one row per group
    "dates",  # time ranges and calendar arithmetic, in UTC
    "ranking",  # top or bottom n
    "windows",  # window functions over ordered rows
    "set_logic",  # never, every, at least one
    "business_definitions",  # a term the question defines ("late", "active")
]

Split = Literal["train", "dev", "heldout"]
Source = Literal["mcp-backbone", "agent-eval-harness", "new"]


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    tags: list[str]
    family: Family
    split: Split
    source: Source
    prompt: str
    reference_sql: str
    # Written separately from reference_sql; must give the same result (C6).
    alternative_sql: str
    # The likeliest wrong reading; must give a different result (C7).
    wrong_sql: str
    # True only when the question asks for the rows in a given order.
    is_ordered: bool = False

    @model_validator(mode="after")
    def _has_one_difficulty(self) -> "Task":
        found = [tag for tag in self.tags if tag in DIFFICULTIES]
        if len(found) != 1:
            raise ValueError(f"task {self.id}: tags need exactly one of {DIFFICULTIES}")
        return self

    @property
    def difficulty(self) -> Difficulty:
        return next(tag for tag in DIFFICULTIES if tag in self.tags)


class TaskFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite: str
    version: int
    description: str
    # Lets anyone spot these tasks in a model's training data (ADR-009).
    canary: str
    tasks: list[Task]

    @model_validator(mode="after")
    def _ids_are_unique(self) -> "TaskFile":
        ids = [task.id for task in self.tasks]
        duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate task ids: {duplicates}")
        return self


def load_task_file(path: Path) -> TaskFile:
    return TaskFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
