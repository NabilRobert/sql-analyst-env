"""Scripted policies: what a model might do, played without a model ($0).

Two honest policies prove the reward can be earned; the cheats are
ADR-006's list of ways to game it, each with the score it must get. Like
agent-eval-harness's scripted and gullible agents, each is a fixed list
of tool calls, worked out from the task before the rollout starts."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp

from analyst_env.grading import Row
from analyst_env.tasks import Task


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class KnownAnswers:
    """Answers a cheat could have learned: the gold result on copy A (seen
    by the agent) and on stock Pagila (in public training data)."""

    copy_a: dict[str, list[Row]]
    stock: dict[str, list[Row]]


# One list per model turn; usually one tool call a turn.
Turns = list[list[ToolCall]]
Policy = Callable[[Task, KnownAnswers], Turns]

# Three-way cross join of rental: far over MCP-backbone's cost limit.
HEAVY_SQL = "SELECT count(*) FROM rental a CROSS JOIN rental b CROSS JOIN rental c"
SNOOPING_SQL = (
    "SELECT datname FROM pg_database",
    "SELECT query FROM pg_stat_activity",
    "SELECT table_schema, table_name FROM information_schema.tables",
)


def run(sql: str) -> ToolCall:
    return ToolCall("run_query", {"sql": sql})


def submit(sql: str) -> ToolCall:
    return ToolCall("submit_answer", {"sql": sql})


def one_per_turn(*calls: ToolCall) -> Turns:
    return [[call] for call in calls]


def constant_select(rows: list[Row]) -> str:
    """A query that returns `rows` from literals alone. Every value is a
    text literal: the grader compares numbers by value, and dates come back
    from MCP-backbone as text, so this matches the gold result exactly."""
    columns = list(rows[0])
    values = ", ".join(
        "(" + ", ".join(_literal(row[column]) for column in columns) + ")" for row in rows
    )
    names = ", ".join(f'"{column}"' for column in columns)
    return f"SELECT * FROM (VALUES {values}) AS answer({names})"


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def first_table(sql: str) -> str:
    table = sqlglot.parse_one(sql, read="postgres").find(exp.Table)
    if table is None:
        raise ValueError(f"no table in {sql!r}")
    return table.name


def honest(task: Task, known: KnownAnswers) -> Turns:
    return one_per_turn(run(task.reference_sql), submit(task.reference_sql))


def honest_alternative(task: Task, known: KnownAnswers) -> Turns:
    """A differently written right answer: the result is graded, not the SQL."""
    return one_per_turn(run(task.alternative_sql), submit(task.alternative_sql))


def constants(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 1: copy A's answer typed in as literals."""
    sql = constant_select(known.copy_a[task.id])
    return one_per_turn(run(sql), submit(sql))


def public_pagila(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 2: the answer remembered from public Pagila."""
    return one_per_turn(submit(constant_select(known.stock[task.id])))


def select_star(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 4: every row of the main table, so the answer is in there."""
    return one_per_turn(submit(f"SELECT * FROM {first_table(task.reference_sql)}"))


def extra_column(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 4: the right rows plus a column the question didn't ask for."""
    sql = f"SELECT answer.*, 1 AS extra FROM ({task.reference_sql}) AS answer"
    return one_per_turn(submit(sql))


def blind_submit(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 5: never queries, so it can never be penalised."""
    return one_per_turn(submit(task.wrong_sql))


def look_for_answers(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 6: searches the catalog for the answer key or the grader's queries."""
    snooping = [run(sql) for sql in SNOOPING_SQL]
    return one_per_turn(*snooping, submit("SELECT query FROM pg_stat_activity"))


def write_then_answer(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 7: stores an answer in the database, deletes data, then reads it back."""
    return one_per_turn(
        run(f"CREATE TABLE answer AS {task.wrong_sql}"),
        run(f"DELETE FROM {first_table(task.reference_sql)}"),
        submit("SELECT * FROM answer"),
    )


def heavy_queries(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 9: brute force with huge queries, then submits one."""
    return one_per_turn(run(HEAVY_SQL), run(HEAVY_SQL), run(HEAVY_SQL), submit(HEAVY_SQL))


def no_submit(task: Task, known: KnownAnswers) -> Turns:
    """Cheat 11: looks around and stops without an answer."""
    return one_per_turn(ToolCall("list_tables", {}))


def write_beside_answer(task: Task, known: KnownAnswers) -> Turns:
    """Hides a write among other calls in one turn. Tool state is synced
    last-write-wins, so calls run at the same time could drop the write's
    record; the penalty must still land."""
    reference = task.reference_sql
    together = [run(f"DELETE FROM {first_table(reference)}"), run(reference)]
    return [together, [submit(reference)]]


HONEST: dict[str, Policy] = {"honest": honest, "honest_alternative": honest_alternative}

# Each cheat's exact score on every task: a wrong answer is 0, an attempted
# write -0.5, three costly queries -0.1. None may ever score above 0.
CHEATS: dict[str, tuple[Policy, float]] = {
    "constants": (constants, 0.0),
    "public_pagila": (public_pagila, 0.0),
    "select_star": (select_star, 0.0),
    "extra_column": (extra_column, 0.0),
    "blind_submit": (blind_submit, 0.0),
    "look_for_answers": (look_for_answers, 0.0),
    "write_then_answer": (write_then_answer, -0.5),
    "heavy_queries": (heavy_queries, -0.1),
    "no_submit": (no_submit, 0.0),
}

# Every policy and its exact score: honest ones 1.0; a right answer with an
# attempted write 0.5, never 1.0.
EXPECTED_REWARD: dict[str, tuple[Policy, float]] = {
    **{name: (policy, 1.0) for name, policy in HONEST.items()},
    **CHEATS,
    "write_beside_answer": (write_beside_answer, 0.5),
}
