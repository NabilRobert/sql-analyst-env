"""G5: our grader gives the same verdict as agent-eval-harness's strict
grader on real answers to the 40 tasks we share (ADR-008).

analyst_env/grading.py is a copy of the harness's strict comparison, so
this checks the copy against the original's own recorded verdicts: every
distinct result a model returned in the harness's committed runs, with
the expected rows and the verdict the harness gave. The verdicts are
extracted by tests/fixtures/extract_harness_verdicts.py."""

import json
from pathlib import Path
from typing import Any

from analyst_env.grading import rows_equal_strict
from analyst_env.tasks import PUBLIC_TASKS, load_task_file

VERDICTS = Path(__file__).parent / "fixtures" / "harness_verdicts.json"


def _verdicts() -> list[dict[str, Any]]:
    return json.loads(VERDICTS.read_text(encoding="utf-8"))["verdicts"]


def test_our_grader_agrees_with_every_harness_verdict() -> None:
    disagreements = [
        (verdict["task_id"], verdict["strict"])
        for verdict in _verdicts()
        if rows_equal_strict(verdict["actual"], verdict["expected"]) != verdict["strict"]
    ]
    assert disagreements == []


def test_the_verdicts_cover_all_40_shared_tasks() -> None:
    shared = {task.id for task in load_task_file(PUBLIC_TASKS).tasks if task.source != "new"}
    assert {verdict["task_id"] for verdict in _verdicts()} == shared


def test_the_verdicts_include_passes_and_failures() -> None:
    """Agreement only on passes (or only on failures) would prove little."""
    assert {verdict["strict"] for verdict in _verdicts()} == {True, False}
