"""Reading a run's traces.jsonl into run records: the shape below is
verifiers 0.4.0's, trimmed to the fields the record reads."""

import json
from pathlib import Path
from typing import Any

from analyst_env.run_record import read_rollouts


def _trace(
    correct: float = 1.0,
    unsafe: float = 0.0,
    expensive: float = 0.0,
    is_ok: bool = True,
    finish_reasons: tuple[str, ...] = ("tool_calls", "stop"),
) -> dict[str, Any]:
    calls = [
        {"finish_reason": reason, "usage": {"prompt_tokens": 100 * turn, "completion_tokens": 50}}
        for turn, reason in enumerate(finish_reasons, start=1)
    ]
    return {
        "ok": is_ok,
        "errors": [],
        "stop_condition": "answer_submitted",
        "rewards": {
            "correct": {"score": correct, "weight": 1.0},
            "unsafe_attempt": {"score": unsafe, "weight": -0.5},
            "expensive_attempts": {"score": expensive, "weight": -0.1},
        },
        "metrics": {"queries_run": 3.0, "has_submitted": 1.0},
        "calls": calls,
        "timing": {"start": 10.0, "scoring": {"start": 30.0, "end": 31.5}},
    }


def _write_traces(tmp_path: Path, episodes: list[tuple[str, list[dict[str, Any]]]]) -> Path:
    lines = [
        json.dumps({"task": {"data": {"id": task_id}}, "errors": [], "traces": traces})
        for task_id, traces in episodes
    ]
    path = tmp_path / "traces.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_a_clean_right_answer_is_recorded_as_correct(tmp_path: Path) -> None:
    [rollout] = read_rollouts(_write_traces(tmp_path, [("e01", [_trace()])]))
    assert rollout.is_correct and not rollout.is_errored
    assert rollout.reward == 1.0
    assert rollout.seconds == 21.5


def test_a_right_answer_after_a_write_keeps_its_penalty(tmp_path: Path) -> None:
    [rollout] = read_rollouts(_write_traces(tmp_path, [("e01", [_trace(unsafe=1.0)])]))
    assert rollout.is_correct and rollout.has_unsafe_attempt
    assert rollout.reward == 0.5


def test_a_failed_rollout_is_errored_not_wrong(tmp_path: Path) -> None:
    [rollout] = read_rollouts(_write_traces(tmp_path, [("e01", [_trace(is_ok=False)])]))
    assert rollout.is_errored


def test_tries_are_numbered_per_task(tmp_path: Path) -> None:
    episodes = [("e01", [_trace()]), ("e02", [_trace()]), ("e01", [_trace(), _trace()])]
    rollouts = read_rollouts(_write_traces(tmp_path, episodes))
    assert [(rollout.task_id, rollout.attempt) for rollout in rollouts] == [
        ("e01", 0),
        ("e02", 0),
        ("e01", 1),
        ("e01", 2),
    ]


def test_the_longest_call_and_a_cut_off_reply_are_recorded(tmp_path: Path) -> None:
    trace = _trace(finish_reasons=("tool_calls", "length"))
    [rollout] = read_rollouts(_write_traces(tmp_path, [("e01", [trace])]))
    assert rollout.max_call_tokens == 250
    assert rollout.has_cut_off_reply


def test_cached_prompt_tokens_count_towards_the_longest_call(tmp_path: Path) -> None:
    trace = _trace()
    trace["calls"] = [
        {
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 5, "cached_input_tokens": 900, "completion_tokens": 50},
        }
    ]
    [rollout] = read_rollouts(_write_traces(tmp_path, [("e01", [trace])]))
    assert rollout.max_call_tokens == 955
