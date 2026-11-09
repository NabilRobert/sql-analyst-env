"""The results table's numbers, and the check that RESULTS.md is exactly
what the committed run records generate."""

import pytest

from analyst_env.results import (
    CALL_TOKEN_LIMIT,
    RESULTS_FILE,
    bootstrap_interval,
    call_limit_line,
    pass_every_try,
    render,
    summarise,
)
from analyst_env.run_record import (
    Environment,
    ModelInfo,
    Rollout,
    RunRecord,
    Sampling,
    load_records,
)


def _rollout(
    task_id: str, is_correct: bool, is_errored: bool = False, max_call_tokens: int = 1000
) -> Rollout:
    return Rollout(
        task_id=task_id,
        attempt=0,
        is_errored=is_errored,
        is_correct=is_correct,
        has_submitted=True,
        has_unsafe_attempt=False,
        has_expensive_attempt=False,
        reward=1.0 if is_correct else 0.0,
        queries_run=2,
        stop_condition="answer_submitted",
        seconds=10.0,
        max_call_tokens=max_call_tokens,
        has_cut_off_reply=False,
    )


def _record(rollouts: list[Rollout]) -> RunRecord:
    model = ModelInfo(
        name="qwen3:1.7b",
        digest="d",
        format="gguf",
        quantization="Q4_K_M",
        parameter_size="2.0B",
        runner="ggml",
        runtime="Ollama 0.40.11",
        context_length=16384,
        is_thinking=True,
        packaged_parameters="",
    )
    environment = Environment(
        commit="0" * 40,
        verifiers_version="0.4.0",
        max_turns=16,
        task_file_sha256="s",
        fingerprints={},
    )
    return RunRecord(
        split="dev",
        tries_per_task=5,
        started_at="2026-11-04T00:00:00+00:00",
        wall_seconds=1.0,
        model=model,
        sampling=Sampling(sent={"temperature": 0.6}, source="card"),
        environment=environment,
        rollouts=rollouts,
    )


def test_pass_at_1_averages_each_task_first() -> None:
    # Task a: 1 of 1; task b: 1 of 3. Per task 1.0 and 1/3, so 2/3, not 2/4.
    rollouts = [_rollout("a", True), *(_rollout("b", passed) for passed in (True, False, False))]
    assert summarise(_record(rollouts)).pass_at_1 == pytest.approx(2 / 3)


def test_errored_tries_are_left_out_of_the_score() -> None:
    summary = summarise(_record([_rollout("a", True), _rollout("a", False, is_errored=True)]))
    assert summary.pass_at_1 == 1.0
    assert summary.errored == 1


def test_the_interval_is_a_point_when_every_try_agrees() -> None:
    assert bootstrap_interval({"a": [True] * 5, "b": [True] * 5}) == (1.0, 1.0)


def test_the_interval_holds_the_estimate_and_repeats_exactly() -> None:
    passes = {f"t{index}": [index % 3 == 0, index % 2 == 0] for index in range(10)}
    low, high = bootstrap_interval(passes)
    assert low < 0.45 < high
    assert bootstrap_interval(passes) == (low, high)


def test_pass_every_try_counts_only_tasks_with_every_try_graded() -> None:
    passes = {"a": [True] * 5, "b": [True, False, True, True, True], "c": [True] * 4}
    assert pass_every_try(passes, tries=5) == (1, 2)


def test_a_right_try_over_the_call_limit_is_listed_with_the_score_without_it() -> None:
    over = _rollout("a", True, max_call_tokens=CALL_TOKEN_LIMIT + 5)
    line = call_limit_line(_record([over, _rollout("b", True)]))
    assert line is not None
    assert "1 try had a call of 22,118 tokens or more (the longest 22,123)" in line
    assert "1 of them was right; counted as wrong, pass@1 would be 50.0%" in line


def test_a_run_within_the_call_limit_has_no_line() -> None:
    under = _rollout("a", True, max_call_tokens=CALL_TOKEN_LIMIT - 1)
    assert call_limit_line(_record([under])) is None


def test_results_file_matches_the_run_records() -> None:
    assert RESULTS_FILE.read_text(encoding="utf-8") == render(load_records()), (
        "RESULTS.md is stale: run `uv run analyst-env results` and commit it"
    )
