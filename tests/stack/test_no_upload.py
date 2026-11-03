"""Nothing uploads or bills: an evaluation run reaches no host outside
this machine (requirement C1, ADR-002).

Each run goes through an egress guard that writes down every outside host
it tries. The first test is the control: the same run with verifiers'
upload switched back on must be caught, which shows the guard sees the
upload path. The second is the real check: run our way, nothing is."""

import os
import subprocess
from pathlib import Path

import pytest

from analyst_env.run_eval import EvalRun, eval_command, eval_environment, run_eval
from tests.scripted.egress import egress_guard, proxy_environment
from tests.scripted.model_server import MODEL_PREFIX, ScriptedModel, serve
from tests.scripted.policies import KnownAnswers
from tests.stack.conftest import public_tasks
from tests.stack.test_cheat_suite import read_rollouts

pytestmark = pytest.mark.stack

TASKS_PER_RUN = 2
PRIME_HOST_SUFFIX = "primeintellect.ai"
NO_ANSWERS = KnownAnswers(copy_a={}, stock={})
HONEST = MODEL_PREFIX + "honest"


def _honest_model() -> ScriptedModel:
    return ScriptedModel(public_tasks(), NO_ANSWERS)


def test_the_guard_catches_a_run_with_upload_switched_on(tmp_path: Path) -> None:
    with egress_guard() as (proxy_url, log), serve(_honest_model()) as url:
        run = EvalRun(HONEST, url, "push-on", tmp_path, TASKS_PER_RUN)
        command = [flag for flag in eval_command(run) if flag != "--no-push"]
        environment = {**eval_environment(), **proxy_environment(proxy_url)}
        # A made-up key: the guard refuses the connection before Prime sees it.
        environment["PRIME_API_KEY"] = "not-a-real-key"
        del environment["PRIME_RUNS_MODE"]
        subprocess.run(command, env=environment, check=True, capture_output=True)
    assert any(host.endswith(PRIME_HOST_SUFFIX) for host in log.refused_hosts)


def test_an_evaluation_run_reaches_no_outside_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with egress_guard() as (proxy_url, log), serve(_honest_model()) as url:
        for name, value in proxy_environment(proxy_url).items():
            monkeypatch.setitem(os.environ, name, value)
        run_dir = run_eval(EvalRun(HONEST, url, "guarded", tmp_path, TASKS_PER_RUN))
    assert log.refused_hosts == set()
    rewards = [rollout.reward for rollout in read_rollouts(run_dir).values()]
    assert rewards == [1.0] * TASKS_PER_RUN
