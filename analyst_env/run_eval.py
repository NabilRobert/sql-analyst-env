"""Runs verifiers' `vf-eval` on this environment, locally and at $0.

Out of the box, `vf-eval` points three ways at paid Prime Intellect
services (checked in verifiers 0.4.0's source, 2026-11-03):
- it uploads the finished run (`push`, on by default; billed per GiB);
- the agent runs in a Prime sandbox (`env.agent.runtime`, default `prime`);
- the model is Prime's hosted inference (`client.base_url`).

So every run here goes through `eval_command`, which turns all three off,
accepts only a model server on this machine, and takes no free-form
flags that could turn them back on. `eval_environment` also hides any
Prime credentials from the run, so even a missed default can't bill."""

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from analyst_env.backbone import REPO_ROOT, ensure_local
from analyst_env.environment import AnalystTaskset
from analyst_env.fingerprint import live_fingerprints, load_stored_fingerprints, mismatch_error

DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"
# verifiers finds the environment by its package name.
TASKSET_ID = AnalystTaskset.__module__.split(".")[0]
# Enough to look at the schema, try a few queries and submit (ADR-006, cheat 9).
MAX_TURNS = 16
# A local model server needs no key; naming our own variable keeps verifiers
# from falling back to a Prime key in the environment or the Prime CLI's config.
MODEL_KEY_VARIABLE = "ANALYST_ENV_MODEL_KEY"
LOCAL_ONLY_FLAGS = (
    "--no-push",
    "--env.agent.runtime.type",
    "subprocess",
    # The plain chat loop: the model gets our tools and nothing else (no bash).
    "--env.agent.harness.id",
    "null",
)


@dataclass(frozen=True)
class EvalRun:
    model: str
    base_url: str
    run_name: str
    output_dir: Path = DEFAULT_OUTPUT_DIR
    num_tasks: int | None = None
    rollouts_per_task: int = 1
    max_concurrent: int = 4


def eval_command(run: EvalRun) -> list[str]:
    ensure_local(run.base_url)
    vf_eval = str(Path(sys.executable).parent / "vf-eval")
    command = [vf_eval, TASKSET_ID, *LOCAL_ONLY_FLAGS]
    command += ["--model", run.model, "--client.base-url", run.base_url]
    command += ["--client.api-key-var", MODEL_KEY_VARIABLE]
    command += ["--env.agent.max-turns", str(MAX_TURNS)]
    command += ["--num-rollouts", str(run.rollouts_per_task)]
    command += ["--max-concurrent", str(run.max_concurrent)]
    command += ["--output-dir", str(run.output_dir), "--run.dir", run.run_name, "--clean"]
    command += ["--no-rich"]
    if run.num_tasks is not None:
        command += ["--select.limit", str(run.num_tasks)]
    return command


def eval_environment() -> dict[str, str]:
    """This process's environment without Prime credentials, and with the
    Prime runs SDK switched off in case anything still asks for it."""
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("PRIME_")
    }
    environment["PRIME_RUNS_MODE"] = "disabled"
    return environment


def _check_fingerprints(moment: str) -> None:
    live = asyncio.run(live_fingerprints())
    stored = load_stored_fingerprints()
    changed = [name for name, digest in live.items() if stored.get(name) != digest]
    if changed:
        raise mismatch_error(changed) from RuntimeError(f"checked {moment} the run")


def run_eval(run: EvalRun) -> Path:
    """Runs one evaluation and returns its directory (traces.jsonl inside).
    The data is fingerprinted before and after, so a run that changed it
    can't pass unnoticed (ADR-006, cheat 7)."""
    _check_fingerprints("before")
    subprocess.run(eval_command(run), env=eval_environment(), check=True)
    _check_fingerprints("after")
    return run.output_dir / run.run_name
