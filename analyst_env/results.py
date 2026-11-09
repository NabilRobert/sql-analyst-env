"""RESULTS.md, generated from the run records in runs/ (ADR-014). A test
regenerates it and fails if the committed file differs, so every number
in it traces to a record.

The 95% interval for pass@1 is agent-eval-harness's bootstrap
(agent_eval/compare.py: bootstrap_interval, commit c7ad5e0), for one run
instead of a difference: resample the tasks, then each task's tries, so
the interval counts both "which tasks" and "which tries" as noise. The
harness can't be a dependency here (its mcp pin clashes with verifiers'),
and it has no one-run version to call."""

import random
import statistics
from collections import defaultdict
from dataclasses import dataclass

from analyst_env.backbone import REPO_ROOT
from analyst_env.baselines import CONTEXT_LENGTH
from analyst_env.run_record import RunRecord, load_records

RESULTS_FILE = REPO_ROOT / "RESULTS.md"
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 13
INTERVAL_LEVEL = 0.95
# Pass rule 2 (docs/guide.md, "When a run counts"): no model call may
# reach 90% of the context window, 22,118 of 24,576 tokens.
CALL_TOKEN_LIMIT = int(0.9 * CONTEXT_LENGTH)
SPLIT_LABELS = {"dev": "dev (public)", "heldout": "held-out (private)", "train": "train"}


@dataclass(frozen=True)
class Summary:
    passes_by_task: dict[str, list[bool]]
    graded: int
    errored: int

    @property
    def pass_at_1(self) -> float:
        return statistics.fmean(_rate(passes) for passes in self.passes_by_task.values())


def summarise(record: RunRecord) -> Summary:
    passes_by_task: dict[str, list[bool]] = defaultdict(list)
    for rollout in record.rollouts:
        if not rollout.is_errored:
            passes_by_task[rollout.task_id].append(rollout.is_correct)
    errored = sum(1 for rollout in record.rollouts if rollout.is_errored)
    graded = len(record.rollouts) - errored
    return Summary(dict(passes_by_task), graded=graded, errored=errored)


def bootstrap_interval(
    passes_by_task: dict[str, list[bool]], seed: int = BOOTSTRAP_SEED
) -> tuple[float, float]:
    rates = [_rate(passes) for passes in passes_by_task.values()]
    tries = [len(passes) for passes in passes_by_task.values()]
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        total = 0.0
        for _ in rates:
            task = rng.randrange(len(rates))
            total += rng.binomialvariate(tries[task], rates[task]) / tries[task]
        means.append(total / len(rates))
    means.sort()
    tail = (1 - INTERVAL_LEVEL) / 2
    low = means[int(tail * BOOTSTRAP_RESAMPLES)]
    high = means[min(BOOTSTRAP_RESAMPLES - 1, int((1 - tail) * BOOTSTRAP_RESAMPLES))]
    return low, high


def pass_every_try(passes_by_task: dict[str, list[bool]], tries: int) -> tuple[int, int]:
    """pass^k: (tasks passed on every try, tasks with all k tries graded)."""
    complete = [passes for passes in passes_by_task.values() if len(passes) == tries]
    return sum(1 for passes in complete if all(passes)), len(complete)


def _rate(passes: list[bool]) -> float:
    return sum(passes) / len(passes)


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _count(flags: list[bool]) -> str:
    return f"{sum(flags)}/{len(flags)}"


def results_row(record: RunRecord) -> str:
    summary = summarise(record)
    low, high = bootstrap_interval(summary.passes_by_task)
    every, complete = pass_every_try(summary.passes_by_task, record.tries_per_task)
    graded = [rollout for rollout in record.rollouts if not rollout.is_errored]
    seconds = statistics.median(rollout.seconds for rollout in graded)
    cells = [
        f"`{record.model.name}`",
        SPLIT_LABELS[record.split],
        f"{_percent(summary.pass_at_1)} ({_percent(low)} to {_percent(high)})",
        f"{every}/{complete}",
        f"{statistics.fmean(rollout.reward for rollout in graded):.3f}",
        _count([rollout.has_submitted for rollout in graded]),
        _count([rollout.has_unsafe_attempt for rollout in graded]),
        _count([rollout.has_expensive_attempt for rollout in graded]),
        str(summary.errored),
        f"{seconds:.0f} s",
    ]
    return "| " + " | ".join(cells) + " |"


RESULTS_HEADER = (
    "| Model | Tasks | Pass@1 (95% interval) | pass^5 | Mean reward | Submitted | "
    "Unsafe attempt | Costly refusal | Errored | Median time |\n"
    "|---|---|---|---|---|---|---|---|---|---|"
)


def provenance_row(record: RunRecord) -> str:
    model = record.model
    cells = [
        f"`{model.name}`",
        record.split,
        f"{model.format} {model.quantization}, {model.runner} runner",
        model.runtime,
        _context(model.context_length, model.runner),
        "on" if model.is_thinking else "no",
        ", ".join(f"{name} {value}" for name, value in record.sampling.sent.items()),
        f"`{record.environment.commit[:7]}`",
        record.started_at[:10],
        f"`runs/{record.split}/{model.name.replace(':', '-')}.json`",
    ]
    return "| " + " | ".join(cells) + " |"


def call_limit_line(record: RunRecord) -> str | None:
    """A run's tries over the call limit, and its pass@1 with any right ones
    counted as wrong; None if no try went over."""
    over = [rollout for rollout in record.rollouts if rollout.max_call_tokens >= CALL_TOKEN_LIMIT]
    if not over:
        return None
    right_over = sum(1 for rollout in over if rollout.is_correct)
    longest = max(rollout.max_call_tokens for rollout in over)
    as_wrong = [
        rollout.model_copy(update={"is_correct": False}) if rollout in over else rollout
        for rollout in record.rollouts
    ]
    without = summarise(record.model_copy(update={"rollouts": as_wrong})).pass_at_1
    tries = "1 try had" if len(over) == 1 else f"{len(over)} tries had"
    were = "was" if right_over == 1 else "were"
    return (
        f"- `{record.model.name}`, {SPLIT_LABELS[record.split]} tasks: {tries} a call "
        f"of {CALL_TOKEN_LIMIT:,} tokens or more (the longest {longest:,}). "
        f"{right_over} of them {were} right; counted as wrong, pass@1 would be {_percent(without)}."
    )


def _context(context_length: int, runner: str) -> str:
    # Ollama reports the configured window for every runner, but its MLX
    # runner doesn't apply it (see "Runs over the call limit").
    if runner == "mlx":
        return f"{context_length:,} reported, not applied"
    return f"{context_length:,}"


PROVENANCE_HEADER = (
    "| Model | Tasks | Weights | Runtime | Context | Thinking | Sampling | Code | Date | Record |\n"
    "|---|---|---|---|---|---|---|---|---|---|"
)


COLUMN_NOTES = """\
- **Pass@1:** the share of tries whose submitted query is right on both data \
copies, averaged per task. **pass^5:** tasks right on all five tries.
- **Mean reward** adds the penalties: -0.5 for a query refused as unsafe, up \
to -0.1 for queries refused for cost or timed out.
- **Submitted:** tries that called `submit_answer`; an answer given only in \
text scores 0. **Errored** tries (an infrastructure failure) are left out of \
every other column.
- The held-out tasks aren't published, so their row can't be rerun by \
others. Pagila's schema is public and these models have likely seen it; the \
data copies defeat memorised answers, not knowledge of the schema."""


CALL_LIMIT_NOTES = """\
Pass rule 2 says no model call may reach 90% of the context window, because \
past the window Ollama's llama.cpp runner drops the start of the prompt. \
Qwen3.5 runs on Ollama's MLX runner instead, which ignores \
`OLLAMA_CONTEXT_LENGTH` although Ollama reports it, so these prompts were \
processed whole, not cut: the tries saw more context than the rule allows, \
not less. Held-out runs once, so the run couldn't be redone; Arthur chose to \
count it, with the breach stated (2026-11-09)."""

SERVER_NOTE = """\
Every run here was measured on MCP-backbone `dd98f06`. The pin then moved to \
`90fa10d`, which accepts top-level UNION, INTERSECT and EXCEPT (the old pin \
refused them as unsafe) and refuses row locks (`FOR UPDATE` now counts as \
unsafe). No try used a row lock and no submitted answer was a set operation, \
so no pass@1 or pass^5 here would change. Some unsafe counts would: \
[the rollout review](docs/rollout-review.md#upstream) has the tries."""


def _call_limit_section(records: list[RunRecord]) -> list[str]:
    lines = [line for line in map(call_limit_line, records) if line is not None]
    if not lines:
        return []
    return ["## Runs over the call limit", "", CALL_LIMIT_NOTES, "", *lines, ""]


def render(records: list[RunRecord]) -> str:
    ordered = sorted(records, key=lambda record: (record.split != "dev", record.model.name))
    lines = [
        "# Results",
        "",
        "Generated by `uv run analyst-env results` from the run records in `runs/`; "
        "a test fails if this file drifts from them. How the numbers are made: "
        "[the guide](docs/guide.md#baselines).",
        "",
        RESULTS_HEADER,
        *(results_row(record) for record in ordered),
        "",
        COLUMN_NOTES,
        "",
        SERVER_NOTE,
        "",
        *_call_limit_section(ordered),
        "## How each run was made",
        "",
        PROVENANCE_HEADER,
        *(provenance_row(record) for record in ordered),
        "",
    ]
    return "\n".join(lines)


def write_results() -> None:
    RESULTS_FILE.write_text(render(load_records()), encoding="utf-8")
