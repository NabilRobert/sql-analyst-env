"""The verifiers environment: each task file entry becomes a verifiers Task
with its rewards (ADR-005).

verifiers (v1) runs a rollout like this: it sends the task's prompt to
the model, the model calls the tools in analyst_env/tools.py, and when it
stops, verifiers calls every `@vf.reward` method here and sums them with
their weights. So: correct and clean = 1.0; correct after an attempted
write = 0.5; wrong = 0; wrong with a write = -0.5."""

from pathlib import Path
from typing import cast

import verifiers.v1 as vf  # pyright: ignore[reportMissingTypeStubs]

from analyst_env import penalties
from analyst_env.scoring import is_correct
from analyst_env.tasks import PUBLIC_TASKS, Split, load_task_file
from analyst_env.tools import AnalystTools, AnalystToolsConfig, RolloutState

SYSTEM_PROMPT = """\
You are a data analyst. Answer the question with the PostgreSQL database \
behind your tools. Explore it with list_tables, describe_table and \
sample_rows, try queries with run_query, then call submit_answer once with \
the one SQL query whose result is the answer.

Your query's result is graded, not your prose: return exactly the columns \
the question asks for, with one row per answer. An answer given only in \
text, without submit_answer, scores 0. The database is read-only."""


class AnalystTaskData(vf.TaskData):
    reference_sql: str
    is_ordered: bool = False


class AnalystTask(vf.Task[AnalystTaskData, RolloutState]):
    @property
    def key(self) -> str:
        # Task ids are durable and unique; the default content hash isn't
        # stable across prompt edits.
        return self.data.id or self.hash

    # verifiers picks a stop hook's kind by the exact class of its parameter,
    # so this one takes a plain `vf.Trace`, not `vf.Trace[...]`.
    @vf.stop
    def answer_submitted(self, trace: vf.Trace) -> bool:  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
        return cast(RolloutState, trace.state).submitted_sql is not None

    # verifiers awaits every reward and metric, so each is async.
    @vf.reward(weight=1.0)
    async def correct(
        self, task: AnalystTaskData, trace: vf.Trace[AnalystTaskData, RolloutState]
    ) -> float:
        submitted_sql = trace.state.submitted_sql
        if submitted_sql is None:
            return 0.0
        is_right = await is_correct(submitted_sql, task.reference_sql, task.is_ordered)
        return 1.0 if is_right else 0.0

    @vf.reward(weight=-0.5)
    async def unsafe_attempt(self, trace: vf.Trace[AnalystTaskData, RolloutState]) -> float:
        return penalties.unsafe_attempt(trace.state.queries)

    @vf.reward(weight=-0.1)
    async def expensive_attempts(self, trace: vf.Trace[AnalystTaskData, RolloutState]) -> float:
        return penalties.expensive_attempts(trace.state.queries)

    @vf.metric
    async def queries_run(self, trace: vf.Trace[AnalystTaskData, RolloutState]) -> float:
        return float(len(trace.state.queries))

    # Small models often write the answer as text instead of submitting it.
    @vf.metric
    async def has_submitted(self, trace: vf.Trace[AnalystTaskData, RolloutState]) -> float:
        return 1.0 if trace.state.submitted_sql is not None else 0.0


class AnalystTasksetConfig(vf.TasksetConfig):
    # Point at the held-out file (outside the repo) to run the held-out tasks.
    task_file: Path = PUBLIC_TASKS
    # None runs every task in the file; baselines run one split at a time.
    split: Split | None = None


# verifiers' generics take State itself, not a subclass of it (they're
# invariant), so pyright can't accept our RolloutState in a few places.
class AnalystTaskset(vf.Taskset[AnalystTask, AnalystTasksetConfig]):  # pyright: ignore[reportInvalidTypeArguments]
    def load(self):  # noqa: ANN201 - verifiers types the return as Iterable[TaskT]
        for task in load_task_file(self.config.task_file).tasks:
            if self.config.split is not None and task.split != self.config.split:
                continue
            data = AnalystTaskData(  # pyright: ignore[reportCallIssue] - pydantic fills defaults
                id=task.id,
                name=task.id,
                prompt=task.prompt,
                system_prompt=SYSTEM_PROMPT,
                reference_sql=task.reference_sql,
                is_ordered=task.is_ordered,
            )
            yield AnalystTask(data, self.config.task)

    @classmethod
    def toolsets(cls, config: AnalystTasksetConfig) -> list[vf.Toolset]:  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
        return [AnalystTools(AnalystToolsConfig())]  # pyright: ignore[reportReturnType]
