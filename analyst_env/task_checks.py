"""The answer-key checks (ADR-008): every task must pass all seven on both
data copies before it can be used for grading or training.

| C1 | the gold SQL passes MCP-backbone's validator and cost check |
| C2 | it returns the same result twice |
| C3 | no tie at a cut (see sql_variants.py) |
| C4 | it returns at least one row and isn't cut off at the row cap |
| C5 | its result differs between the copies, so constants can't pass |
| C6 | a second, separately written query gives the same result |
| C7 | the likeliest wrong reading gives a different result |

Every query goes through MCP-backbone, exactly as an agent's would."""

import asyncio
from dataclasses import dataclass

from analyst_env.backbone import BackboneCopy, QueryResult, open_copies
from analyst_env.fingerprint import load_stored_fingerprints, mismatch_error, mismatched_copies
from analyst_env.grading import Row, results_match
from analyst_env.sql_variants import tie_break_variants
from analyst_env.tasks import Task

# Tasks checked at once over the same sessions. Each run_query costs about
# 180 ms in MCP-backbone (validate, cost check, connect, audit), so one at a
# time takes about a minute for 40 tasks.
PARALLEL_TASKS = 4


@dataclass(frozen=True)
class CheckFailure:
    check: str  # "C1" to "C7"
    copy: str  # the data copy it failed on, or "both"
    reason: str

    def __str__(self) -> str:
        return f"{self.check} on {self.copy}: {self.reason}"


async def check_tasks(
    tasks: list[Task], url: str, keys: dict[str, str]
) -> dict[str, list[CheckFailure]]:
    """Every task's failures, by task id, after checking that the copies
    hold the data the stored fingerprints describe."""
    async with open_copies(url, keys) as copies:
        mismatched = await mismatched_copies(copies, load_stored_fingerprints())
        if not mismatched:
            return await _check_in_parallel(tasks, copies)
    raise mismatch_error(mismatched)


async def _check_in_parallel(
    tasks: list[Task], copies: list[BackboneCopy]
) -> dict[str, list[CheckFailure]]:
    slots = asyncio.Semaphore(PARALLEL_TASKS)

    async def check_one(task: Task) -> tuple[str, list[CheckFailure]]:
        async with slots:
            return task.id, await check_task(task, copies)

    return dict(await asyncio.gather(*(check_one(task) for task in tasks)))


async def check_task(task: Task, copies: list[BackboneCopy]) -> list[CheckFailure]:
    """All failures for one task. C1 and C4 failures stop the rest, since
    every later check compares against the gold result."""
    gold: dict[str, list[Row]] = {}
    failures: list[CheckFailure] = []
    for copy in copies:
        result = await copy.run_query(task.reference_sql)
        failure = _gold_usable(result, copy.name)
        if failure:
            failures.append(failure)
        else:
            gold[copy.name] = result.rows
    if failures:
        return failures

    for copy in copies:
        failures += await _check_copy(task, copy, gold[copy.name])
    failures += _check_copies_differ(task, gold)
    failures += await _check_wrong_reading(task, copies, gold)
    return failures


def _gold_usable(result: QueryResult, copy_name: str) -> CheckFailure | None:
    """C1 and C4."""
    if not result.is_success:
        return CheckFailure("C1", copy_name, f"gold SQL {result.status}: {result.error}")
    if result.truncated:
        return CheckFailure("C4", copy_name, "gold result is cut off at the row cap")
    if not result.rows:
        return CheckFailure("C4", copy_name, "gold result is empty")
    return None


async def _check_copy(task: Task, copy: BackboneCopy, gold: list[Row]) -> list[CheckFailure]:
    """C2, C3 and C6 on one copy."""
    failures: list[CheckFailure] = []
    again = await copy.run_query(task.reference_sql)
    if not results_match(again.rows, gold, task.is_ordered):
        failures.append(CheckFailure("C2", copy.name, "gold SQL gave a different result twice"))

    variants = tie_break_variants(task.reference_sql)
    for variant_sql in variants or ():
        variant = await copy.run_query(variant_sql)
        if not variant.is_success or not results_match(variant.rows, gold, task.is_ordered):
            failures.append(CheckFailure("C3", copy.name, "a tie at the cut changes the answer"))
            break

    alternative = await copy.run_query(task.alternative_sql)
    if not alternative.is_success:
        failures.append(
            CheckFailure(
                "C6", copy.name, f"alternative SQL {alternative.status}: {alternative.error}"
            )
        )
    elif not results_match(alternative.rows, gold, task.is_ordered):
        failures.append(CheckFailure("C6", copy.name, "alternative SQL gives a different result"))
    return failures


def _check_copies_differ(task: Task, gold: dict[str, list[Row]]) -> list[CheckFailure]:
    """C5: one fixed answer must not be right on every copy."""
    results = list(gold.values())
    first = results[0]
    if all(results_match(other, first, task.is_ordered) for other in results[1:]):
        return [CheckFailure("C5", "both", f"same result on every copy: {first}")]
    return []


async def _check_wrong_reading(
    task: Task, copies: list[BackboneCopy], gold: dict[str, list[Row]]
) -> list[CheckFailure]:
    """C7: the wrong reading must run, and must miss on at least one copy,
    since an answer only scores if it matches on all of them. A wrong
    reading that doesn't run proves nothing, so it fails the check."""
    is_caught = False
    for copy in copies:
        wrong = await copy.run_query(task.wrong_sql)
        if not wrong.is_success:
            return [CheckFailure("C7", copy.name, f"wrong reading {wrong.status}: {wrong.error}")]
        if not results_match(wrong.rows, gold[copy.name], task.is_ordered):
            is_caught = True
    if is_caught:
        return []
    return [CheckFailure("C7", "both", "the wrong reading gives the gold result on every copy")]
