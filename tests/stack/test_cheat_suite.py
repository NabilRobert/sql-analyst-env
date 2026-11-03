"""The cheat suite (ADR-006): every scripted policy plays every public
task through the real `vf-eval`, against the local stack, with a scripted
stand-in for the model. The honest policies must score 1.0 everywhere, so
the reward can be earned; each cheat must score exactly what its defence
allows, and none above 0, so it can't be gamed."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from analyst_env.backbone import connect, mcp_url
from analyst_env.grading import Row, results_match
from analyst_env.run_eval import EvalRun, run_eval
from analyst_env.tasks import Task
from tests.scripted.model_server import MODEL_PREFIX, ScriptedModel, serve
from tests.scripted.policies import CHEATS, EXPECTED_REWARD, KnownAnswers, constant_select
from tests.stack.conftest import public_tasks

pytestmark = pytest.mark.stack

# Each run already plays several rollouts at once; more runs than this just
# queue for the same CPU.
PARALLEL_POLICIES = 3
STOCK_PAGILA = "pagila"


@dataclass(frozen=True)
class Rollout:
    is_ok: bool
    reward: float


async def _gold_rows(copy_name: str, key: str, tasks: list[Task]) -> dict[str, list[Row]]:
    async with connect(copy_name, mcp_url(), key) as copy:
        return {task.id: (await copy.run_query(task.reference_sql)).rows for task in tasks}


@pytest.fixture(scope="session")
def known_answers(stack_keys: dict[str, str]) -> KnownAnswers:
    tasks = public_tasks()
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
        rollouts[episode["task"]["data"]["id"]] = Rollout(is_ok=is_ok, reward=reward)
    return rollouts


@pytest.fixture(scope="session")
def suite_rollouts(
    known_answers: KnownAnswers, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, dict[str, Rollout]]:
    output_dir = tmp_path_factory.mktemp("cheat-suite")
    with serve(ScriptedModel(public_tasks(), known_answers)) as base_url:

        def play(policy: str) -> Path:
            model = MODEL_PREFIX + policy
            return run_eval(EvalRun(model, base_url, policy, output_dir, max_concurrent=8))

        with ThreadPoolExecutor(PARALLEL_POLICIES) as pool:
            run_dirs = dict(zip(EXPECTED_REWARD, pool.map(play, EXPECTED_REWARD), strict=True))
    return {policy: read_rollouts(run_dir) for policy, run_dir in run_dirs.items()}


@pytest.mark.parametrize("policy", EXPECTED_REWARD)
def test_policy_scores_exactly_its_expected_reward_on_every_task(
    policy: str, suite_rollouts: dict[str, dict[str, Rollout]]
) -> None:
    _, expected = EXPECTED_REWARD[policy]
    rollouts = suite_rollouts[policy]
    assert sorted(rollouts) == sorted(task.id for task in public_tasks())
    assert [task_id for task_id, rollout in rollouts.items() if not rollout.is_ok] == []
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
            for task in public_tasks():
                gold = known_answers.copy_a[task.id]
                result = await copy.run_query(constant_select(gold))
                if not results_match(result.rows, gold, task.is_ordered):
                    missed.append(task.id)
            return missed

    assert asyncio.run(misses()) == []
