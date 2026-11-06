"""The cheat suite (ADR-006): every scripted policy plays every task
(public, plus held-out where its file is set) through the real `vf-eval`,
against the local stack, with a scripted stand-in for the model. The
honest policies must score 1.0 everywhere, so the reward can be earned;
each cheat must score exactly what its defence allows, and none above 0,
so it can't be gamed."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from analyst_env.backbone import connect, mcp_url
from analyst_env.grading import Row, results_match
from analyst_env.run_eval import EvalRun, run_eval
from analyst_env.tasks import PUBLIC_TASKS, Task, heldout_task_file
from tests.scripted.model_server import MODEL_PREFIX, ScriptedModel, serve
from tests.scripted.policies import CHEATS, EXPECTED_REWARD, KnownAnswers, constant_select
from tests.stack.conftest import all_tasks

pytestmark = pytest.mark.stack

# Each run already plays several rollouts at once; more runs than this just
# queue for the same CPU.
PARALLEL_POLICIES = 3
STOCK_PAGILA = "pagila"
# A harness error's message is a traceback, cause last, and pytest cuts a
# long assertion message short, so only the end of each one is kept.
ERROR_TAIL_CHARACTERS = 300


@dataclass(frozen=True)
class Rollout:
    reward: float
    # What went wrong in an errored rollout, as verifiers wrote it; None if ok.
    error: str | None = None


def _error_summary(errors: list[dict[str, str]] | None) -> str:
    if not errors:
        return "not ok, with no error recorded"
    first = errors[0]
    return f"{first.get('type')}: …{str(first.get('message'))[-ERROR_TAIL_CHARACTERS:]}"


async def _gold_rows(copy_name: str, key: str, tasks: list[Task]) -> dict[str, list[Row]]:
    async with connect(copy_name, mcp_url(), key) as copy:
        return {task.id: (await copy.run_query(task.reference_sql)).rows for task in tasks}


def task_files() -> list[Path]:
    heldout = heldout_task_file()
    return [PUBLIC_TASKS] if heldout is None else [PUBLIC_TASKS, heldout]


@pytest.fixture(scope="session")
def known_answers(stack_keys: dict[str, str]) -> KnownAnswers:
    tasks = all_tasks()
    copy_a = asyncio.run(_gold_rows("copy_a", stack_keys["copy_a"], tasks))
    stock = asyncio.run(_gold_rows(STOCK_PAGILA, stack_keys[STOCK_PAGILA], tasks))
    return KnownAnswers(copy_a=copy_a, stock=stock)


def read_rollouts(run_dir: Path) -> dict[str, Rollout]:
    """Each task's rollout from a run's traces.jsonl: one rollout a task."""
    rollouts: dict[str, Rollout] = {}
    for line in (run_dir / "traces.jsonl").read_text().splitlines():
        episode = json.loads(line)
        trace = episode["traces"][0]
        parts = trace["rewards"].values()
        reward = sum(part["score"] * part["weight"] for part in parts if part is not None)
        is_ok = bool(trace["ok"]) and not episode["errors"]
        error = None if is_ok else _error_summary(episode["errors"] or trace.get("errors"))
        rollouts[episode["task"]["data"]["id"]] = Rollout(reward=reward, error=error)
    return rollouts


@pytest.fixture(scope="session")
def suite_rollouts(
    known_answers: KnownAnswers, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, dict[str, Rollout]]:
    output_dir = tmp_path_factory.mktemp("cheat-suite")
    runs = [(policy, task_file) for policy in EXPECTED_REWARD for task_file in task_files()]
    with serve(ScriptedModel(all_tasks(), known_answers)) as base_url:

        def play(policy_and_file: tuple[str, Path]) -> tuple[str, Path]:
            policy, task_file = policy_and_file
            run = EvalRun(
                MODEL_PREFIX + policy,
                base_url,
                f"{policy}-{task_file.stem}",
                output_dir,
                max_concurrent=8,
                task_file=task_file,
            )
            return policy, run_eval(run)

        with ThreadPoolExecutor(PARALLEL_POLICIES) as pool:
            played = list(pool.map(play, runs))
    rollouts: dict[str, dict[str, Rollout]] = {policy: {} for policy in EXPECTED_REWARD}
    for policy, run_dir in played:
        rollouts[policy].update(read_rollouts(run_dir))
    return rollouts


@pytest.mark.parametrize("policy", EXPECTED_REWARD)
def test_policy_scores_exactly_its_expected_reward_on_every_task(
    policy: str, suite_rollouts: dict[str, dict[str, Rollout]]
) -> None:
    _, expected = EXPECTED_REWARD[policy]
    rollouts = suite_rollouts[policy]
    assert sorted(rollouts) == sorted(task.id for task in all_tasks())
    errored = {task_id: rollout.error for task_id, rollout in rollouts.items() if rollout.error}
    assert errored == {}
    off_target = {
        task_id: rollout.reward
        for task_id, rollout in rollouts.items()
        if rollout.reward != pytest.approx(expected)
    }
    assert off_target == {}


def test_no_cheat_ever_scores_above_zero(suite_rollouts: dict[str, dict[str, Rollout]]) -> None:
    best = {cheat: max(r.reward for r in suite_rollouts[cheat].values()) for cheat in CHEATS}
    assert {cheat: reward for cheat, reward in best.items() if reward > 0} == {}


def test_copy_a_constants_would_pass_without_copy_b(
    stack_keys: dict[str, str], known_answers: KnownAnswers
) -> None:
    """The constants cheat is right on the copy the agent saw, so copy B is
    what stops it, not a flaw in how the cheat was written."""

    async def misses() -> list[str]:
        async with connect("copy_a", mcp_url(), stack_keys["copy_a"]) as copy:
            missed: list[str] = []
            for task in all_tasks():
                gold = known_answers.copy_a[task.id]
                result = await copy.run_query(constant_select(gold))
                if not results_match(result.rows, gold, task.is_ordered):
                    missed.append(task.id)
            return missed

    assert asyncio.run(misses()) == []
