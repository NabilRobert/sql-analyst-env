"""The baselines (ADR-010): three local models through Ollama, five tries
per task, on dev first and then once on held-out. Each run leaves a run
record in runs/ (analyst_env/run_record.py), and RESULTS.md is generated
from those records.

Ollama must already be serving (see the guide): this module asks it what
it's running, so the record says exactly which model, quantisation,
runtime version and context window produced the numbers (requirement M3)."""

import hashlib
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx2

from analyst_env.backbone import REPO_ROOT
from analyst_env.fingerprint import load_stored_fingerprints
from analyst_env.run_eval import DEFAULT_OUTPUT_DIR, MAX_TURNS, EvalRun, run_eval
from analyst_env.run_record import Environment, ModelInfo, RunRecord, Sampling, read_rollouts
from analyst_env.tasks import PUBLIC_TASKS, Split, heldout_task_file

OLLAMA_URL = "http://127.0.0.1:11434"
TRIES_PER_TASK = 5
# Long enough for a schema, a few results and Qwen's thinking; Ollama's
# default (4,096 on this Mac) would drop the start of a long rollout.
CONTEXT_LENGTH = 16384
# Matches OLLAMA_NUM_PARALLEL. One at a time: the Mac is shared, and heavy jobs
# run one at a time (Arthur, 2026-11-04).
PARALLEL_ROLLOUTS = 1
OLLAMA_START = f"OLLAMA_CONTEXT_LENGTH={CONTEXT_LENGTH} OLLAMA_NUM_PARALLEL={PARALLEL_ROLLOUTS}"


@dataclass(frozen=True)
class BaselineModel:
    name: str
    # Each model's recommended settings (ADR-010), sent with every request.
    sampling: dict[str, float]
    settings_source: str


BASELINE_MODELS = (
    BaselineModel(
        "qwen3:1.7b", {"temperature": 0.6, "top_p": 0.95}, "Qwen3 model card, thinking mode"
    ),
    BaselineModel(
        "qwen3.5:4b",
        {"temperature": 1.0, "top_p": 0.95, "presence_penalty": 1.5},
        "Qwen3.5 model card, thinking mode, general tasks",
    ),
    BaselineModel(
        "llama3.2:3b",
        {"temperature": 0.6, "top_p": 0.9},
        "Llama 3.2 3B Instruct generation_config.json",
    ),
)


def find_model(name: str) -> BaselineModel:
    for model in BASELINE_MODELS:
        if model.name == name:
            return model
    names = ", ".join(model.name for model in BASELINE_MODELS)
    raise ValueError(f"{name} isn't a baseline model: pick one of {names}")


def run_baseline(model: BaselineModel, split: Split) -> RunRecord:
    """Runs one model on one split and returns its record (not yet written)."""
    commit = _clean_commit()
    task_file = _task_file(split)
    model_info = ollama_model_info(model.name)
    run = EvalRun(
        model=model.name,
        base_url=f"{OLLAMA_URL}/v1",
        run_name=f"{split}-{model.name.replace(':', '-')}",
        output_dir=_output_dir(split, task_file),
        rollouts_per_task=TRIES_PER_TASK,
        max_concurrent=PARALLEL_ROLLOUTS,
        task_file=task_file,
        split=split,
        sampling=model.sampling,
    )
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    started = time.monotonic()
    run_dir = run_eval(run)
    return RunRecord(
        split=split,
        tries_per_task=TRIES_PER_TASK,
        started_at=started_at,
        wall_seconds=round(time.monotonic() - started, 1),
        model=model_info,
        sampling=Sampling(sent=model.sampling, source=model.settings_source),
        environment=Environment(
            commit=commit,
            verifiers_version=version("verifiers"),
            max_turns=MAX_TURNS,
            task_file_sha256=hashlib.sha256(task_file.read_bytes()).hexdigest(),
            fingerprints=load_stored_fingerprints(),
        ),
        rollouts=read_rollouts(run_dir / "traces.jsonl"),
    )


def _task_file(split: Split) -> Path:
    if split != "heldout":
        return PUBLIC_TASKS
    heldout = heldout_task_file()
    if heldout is None:
        raise RuntimeError(
            "the held-out tasks aren't in the repo: set ANALYST_ENV_HELDOUT_FILE to their file"
        )
    return heldout


def _output_dir(split: Split, task_file: Path) -> Path:
    """Traces hold every prompt, so held-out traces stay beside the held-out file."""
    return task_file.parent / "outputs" if split == "heldout" else DEFAULT_OUTPUT_DIR


def _clean_commit() -> str:
    """The commit that's running, refusing uncommitted changes, so the record
    names the exact code behind its numbers."""

    def git(*arguments: str) -> str:
        command = ["git", "-C", str(REPO_ROOT), *arguments]
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout

    if git("status", "--porcelain").strip():
        raise RuntimeError("the repo has uncommitted changes: commit them first, then run again")
    return git("rev-parse", "HEAD").strip()


def ollama_model_info(name: str) -> ModelInfo:
    """What Ollama is serving under `name`, loading it first so its context
    window can be read back and checked."""
    with httpx2.Client(base_url=OLLAMA_URL, timeout=300) as client:
        shown = client.post("/api/show", json={"model": name}).raise_for_status()
        show: dict[str, Any] = shown.json()
        client.post("/api/generate", json={"model": name}).raise_for_status()
        loaded = client.get("/api/ps").raise_for_status().json()["models"]
        runtime = "Ollama " + client.get("/api/version").raise_for_status().json()["version"]
        tags = client.get("/api/tags").raise_for_status().json()["models"]
    context_length = next(int(model["context_length"]) for model in loaded if model["name"] == name)
    if context_length != CONTEXT_LENGTH:
        raise RuntimeError(
            f"Ollama gives {name} a {context_length}-token context, not {CONTEXT_LENGTH}: "
            f"restart it as `{OLLAMA_START} ollama serve`"
        )
    tag = next(model for model in tags if model["name"] == name)
    details = show["details"]
    return ModelInfo(
        name=name,
        digest=tag["digest"],
        format=details["format"],
        quantization=details["quantization_level"],
        parameter_size=details["parameter_size"],
        runner=tag["details"].get("runner", "unknown"),
        runtime=runtime,
        context_length=context_length,
        # No request asks otherwise, so the model's default applies.
        is_thinking=bool(show.get("thinking", {}).get("default", False)),
        packaged_parameters=show.get("parameters", ""),
    )
