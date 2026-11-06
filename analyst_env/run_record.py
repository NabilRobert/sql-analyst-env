"""Run records: what a baseline run leaves in the repo (requirements M2, M3).

verifiers writes a traces.jsonl per run, with every prompt, tool call and
row the model saw. That stays outside the repo (and, for held-out tasks,
outside it entirely). The record keeps only the numbers: per rollout, its
task id, its reward parts and its timings; per run, the model, runtime,
settings and data fingerprints. RESULTS.md is generated from these files.

The record carries no prompt, SQL or result, so a held-out record can be
committed without publishing a held-out task (ADR-009)."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from analyst_env.backbone import REPO_ROOT
from analyst_env.tasks import Split

RUNS_DIR = REPO_ROOT / "runs"
RECORD_VERSION = 1


class Rollout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    attempt: int
    # An infrastructure failure: left out of every score (requirement O1).
    is_errored: bool
    is_correct: bool
    has_submitted: bool
    has_unsafe_attempt: bool
    # A query refused for cost, or timed out.
    has_expensive_attempt: bool
    reward: float
    queries_run: int
    stop_condition: str | None
    seconds: float
    # The longest single model call, prompt plus reply, to check nothing
    # outgrew the context window (Ollama drops the start of a long prompt).
    max_call_tokens: int
    # A reply cut off by the token limit, not ended by the model.
    has_cut_off_reply: bool


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    digest: str
    format: str
    quantization: str
    parameter_size: str
    runner: str
    runtime: str
    context_length: int
    is_thinking: bool
    # Ollama's own defaults for the model, as `ollama show --parameters` prints them.
    packaged_parameters: str


class Sampling(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # What each request carried; anything else came from packaged_parameters.
    sent: dict[str, int | float]
    source: str


class Environment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commit: str
    verifiers_version: str
    max_turns: int
    task_file_sha256: str
    fingerprints: dict[str, str]


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_version: int = RECORD_VERSION
    split: Split
    tries_per_task: int
    started_at: str
    wall_seconds: float
    model: ModelInfo
    sampling: Sampling
    environment: Environment
    rollouts: list[Rollout]


def record_path(split: Split, model_name: str) -> Path:
    return RUNS_DIR / split / f"{model_name.replace(':', '-')}.json"


def write_record(record: RunRecord) -> Path:
    path = record_path(record.split, record.model.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_records(runs_dir: Path = RUNS_DIR) -> list[RunRecord]:
    paths = sorted(runs_dir.glob("*/*.json"))
    return [RunRecord.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]


def read_rollouts(traces_path: Path) -> list[Rollout]:
    """Every rollout in a run's traces.jsonl, numbered per task."""
    rollouts: list[Rollout] = []
    attempts: dict[str, int] = {}
    for line in traces_path.read_text(encoding="utf-8").splitlines():
        episode = json.loads(line)
        task_id = str(episode["task"]["data"]["id"])
        for trace in episode["traces"]:
            attempt = attempts.get(task_id, 0)
            attempts[task_id] = attempt + 1
            has_episode_errors = bool(episode["errors"])
            rollouts.append(_rollout(task_id, attempt, trace, has_episode_errors))
    return rollouts


def run_timing(traces_path: Path) -> tuple[str, float]:
    """When a finished run started (UTC, ISO) and how long its rollouts took,
    from the traces alone: for a record built after the run.
    It leaves out the fingerprint checks either side, so it's a little
    shorter than a live run's wall time."""
    starts: list[float] = []
    ends: list[float] = []
    for line in traces_path.read_text(encoding="utf-8").splitlines():
        for trace in json.loads(line)["traces"]:
            starts.append(trace["timing"]["start"])
            ends.append(trace["timing"]["scoring"]["end"])
    started_at = datetime.fromtimestamp(min(starts), UTC).isoformat(timespec="seconds")
    return started_at, round(max(ends) - min(starts), 1)


def missing_tries(rollouts: list[Rollout], task_ids: list[str], tries: int) -> list[str]:
    """Tasks with fewer than `tries` rollouts: a run that stopped early."""
    counts = Counter(rollout.task_id for rollout in rollouts)
    return [task_id for task_id in task_ids if counts[task_id] < tries]


def _rollout(
    task_id: str, attempt: int, trace: dict[str, Any], has_episode_errors: bool
) -> Rollout:
    rewards = {name: part for name, part in trace["rewards"].items() if part is not None}
    metrics = trace["metrics"]
    calls = trace["calls"]
    timing = trace["timing"]
    return Rollout(
        task_id=task_id,
        attempt=attempt,
        is_errored=has_episode_errors or bool(trace["errors"]) or not trace["ok"],
        is_correct=_score(rewards, "correct") == 1.0,
        has_submitted=metrics.get("has_submitted") == 1.0,
        has_unsafe_attempt=_score(rewards, "unsafe_attempt") > 0,
        has_expensive_attempt=_score(rewards, "expensive_attempts") > 0,
        reward=sum(part["score"] * part["weight"] for part in rewards.values()),
        queries_run=round(metrics.get("queries_run", 0)),
        stop_condition=trace.get("stop_condition"),
        seconds=timing["scoring"]["end"] - timing["start"],
        max_call_tokens=max((_call_tokens(call) for call in calls), default=0),
        has_cut_off_reply=any(call.get("finish_reason") == "length" for call in calls),
    )


def _score(rewards: dict[str, Any], name: str) -> float:
    part = rewards.get(name)
    return float(part["score"]) if part else 0.0


def _call_tokens(call: dict[str, Any]) -> int:
    usage: dict[str, Any] = call.get("usage") or {}
    # verifiers counts the cached part of the prompt separately, so the
    # prompt's full length is prompt_tokens plus cached_input_tokens.
    prompt_tokens = int(usage.get("prompt_tokens", 0)) + int(usage.get("cached_input_tokens", 0))
    return prompt_tokens + int(usage.get("completion_tokens", 0))
