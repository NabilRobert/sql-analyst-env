"""The taskset: which tasks a run gets."""

from analyst_env.environment import AnalystTaskset, AnalystTasksetConfig
from analyst_env.tasks import PUBLIC_TASKS, load_task_file


def test_a_split_runs_only_its_own_tasks() -> None:
    dev_ids = {task.id for task in load_task_file(PUBLIC_TASKS).tasks if task.split == "dev"}
    loaded = AnalystTaskset(AnalystTasksetConfig(split="dev")).load()
    assert {task.data.id for task in loaded} == dev_ids


def test_no_split_runs_every_task() -> None:
    loaded = list(AnalystTaskset(AnalystTasksetConfig()).load())
    assert len(loaded) == len(load_task_file(PUBLIC_TASKS).tasks)
