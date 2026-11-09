"""The held-out file (ADR-007, ADR-009): where it may live, and its shape.

The shape tests need the file itself, so they run only where
ANALYST_ENV_HELDOUT_FILE points at it (Arthur's machine, not CI)."""

import subprocess
from collections import Counter
from pathlib import Path

import pytest

from analyst_env.backbone import REPO_ROOT
from analyst_env.tasks import (
    HELDOUT_FILE_VARIABLE,
    HELDOUT_ONLY_FAMILIES,
    PUBLIC_TASKS,
    Task,
    heldout_task_file,
    load_task_file,
)

EXPECTED_HELDOUT_TASKS = 30
NEW_TASKS = 60  # the held-out 30 are drawn from these


def test_no_file_means_public_tasks_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HELDOUT_FILE_VARIABLE, raising=False)
    assert heldout_task_file() is None


def test_a_file_inside_the_repo_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HELDOUT_FILE_VARIABLE, str(REPO_ROOT / "tasks" / "private" / "heldout.yaml"))
    with pytest.raises(ValueError, match="outside it"):
        heldout_task_file()


def test_a_missing_file_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(HELDOUT_FILE_VARIABLE, str(tmp_path / "missing.yaml"))
    with pytest.raises(FileNotFoundError, match="doesn't exist"):
        heldout_task_file()


@pytest.fixture
def heldout() -> list[Task]:
    path = heldout_task_file()
    if path is None:
        pytest.skip(f"{HELDOUT_FILE_VARIABLE} is not set")
    return load_task_file(path).tasks


def test_heldout_file_holds_30_new_heldout_tasks(heldout: list[Task]) -> None:
    assert len(heldout) == EXPECTED_HELDOUT_TASKS
    assert {(task.split, task.source) for task in heldout} == {("heldout", "new")}


def test_heldout_ids_are_not_public(heldout: list[Task]) -> None:
    public_ids = {task.id for task in load_task_file(PUBLIC_TASKS).tasks}
    assert public_ids.isdisjoint(task.id for task in heldout)


def test_heldout_holds_every_held_out_only_family(heldout: list[Task]) -> None:
    assert set(HELDOUT_ONLY_FAMILIES) <= {task.family for task in heldout}


def test_heldout_is_stratified_by_difficulty(heldout: list[Task]) -> None:
    """Each difficulty's share of held-out is its share of the 60 new tasks,
    to within one task."""
    public_new = [task for task in load_task_file(PUBLIC_TASKS).tasks if task.source == "new"]
    new_counts = Counter(task.difficulty for task in [*public_new, *heldout])
    heldout_counts = Counter(task.difficulty for task in heldout)
    for difficulty, new_count in new_counts.items():
        fair_share = new_count * EXPECTED_HELDOUT_TASKS / NEW_TASKS
        assert abs(heldout_counts[difficulty] - fair_share) <= 1, difficulty


def test_heldout_canary_differs_from_the_public_one(heldout: list[Task]) -> None:
    path = heldout_task_file()
    assert path is not None
    assert load_task_file(path).canary != load_task_file(PUBLIC_TASKS).canary


def _files_git_would_commit() -> list[Path]:
    command = [
        "git",
        "-C",
        str(REPO_ROOT),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
    ]
    names = subprocess.run(command, check=True, capture_output=True, text=True).stdout.split()
    return [REPO_ROOT / name for name in names if (REPO_ROOT / name).is_file()]


def test_no_heldout_text_is_in_the_repo(heldout: list[Task]) -> None:
    """Run records and RESULTS.md come from held-out runs, so check that none
    of them, nor any other file git would commit, quotes a held-out task."""
    path = heldout_task_file()
    assert path is not None
    secrets = [load_task_file(path).canary]
    for task in heldout:
        secrets += [task.prompt, task.reference_sql, task.alternative_sql, task.wrong_sql]
    for file in _files_git_would_commit():
        text = file.read_text(encoding="utf-8", errors="ignore")
        leaked = [secret[:40] for secret in secrets if secret.strip() in text]
        assert not leaked, f"{file.relative_to(REPO_ROOT)} quotes held-out text: {leaked}"
