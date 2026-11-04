"""Regenerates harness_verdicts.json, the evidence for the G5 agreement
test (tests/test_harness_agreement.py).

agent-eval-harness commits every trial it grades, with the rows the agent's
query returned, the expected rows and its strict grader's verdict. This
script reads those records at the commit our grader was copied from, keeps
the `run_query` results on the 40 Pagila tasks we share, and drops exact
repeats. Run it with a checkout of the harness:

    uv run python tests/fixtures/extract_harness_verdicts.py ~/path/to/agent-eval-harness"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from analyst_env.tasks import PUBLIC_TASKS, load_task_file

# The commit analyst_env/grading.py was copied from (grader version 4).
HARNESS_COMMIT = "a44cad49f5bec0fa4ca29cb46b4ce495a507cfae"
GRADER_VERSION = "4"
OUTPUT = Path(__file__).with_name("harness_verdicts.json")


def git_show(harness: Path, path: str) -> str:
    command = ["git", "-C", str(harness), "show", f"{HARNESS_COMMIT}:{path}"]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def trial_files(harness: Path) -> list[str]:
    command = ["git", "-C", str(harness), "ls-tree", "-r", "--name-only", HARNESS_COMMIT, "runs"]
    listing = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    return [path for path in listing.splitlines() if path.endswith("trials.jsonl")]


def verdicts_in(trial: dict[str, Any], shared_ids: set[str]) -> list[dict[str, Any]]:
    if trial["task_id"] not in shared_ids or str(trial["grader_version"]) != GRADER_VERSION:
        return []
    found: list[dict[str, Any]] = []
    for grader in trial["graders"]:
        # None means the agent never got a result, which no grader compares.
        if grader["kind"] != "result_match" or grader["input"]["graded_rows"] is None:
            continue
        found.append(
            {
                "task_id": trial["task_id"],
                "actual": grader["input"]["graded_rows"],
                "expected": grader["expected"],
                "strict": grader["strict"],
            }
        )
    return found


def main(harness: Path) -> None:
    shared_ids = {task.id for task in load_task_file(PUBLIC_TASKS).tasks if task.source != "new"}
    unique: dict[str, dict[str, Any]] = {}
    for path in trial_files(harness):
        for line in git_show(harness, path).splitlines():
            for verdict in verdicts_in(json.loads(line), shared_ids):
                # Never sort_keys: column order is part of what strict grading compares.
                unique[json.dumps(verdict)] = verdict
    lines = sorted(unique)
    # One verdict a line, so a regenerated file diffs line by line.
    header = json.dumps({"harness_commit": HARNESS_COMMIT, "grader_version": GRADER_VERSION})
    body = ",\n".join(lines)
    OUTPUT.write_text(f'{header[:-1]}, "verdicts": [\n{body}\n]}}\n', encoding="utf-8")
    print(f"wrote {len(lines)} verdicts to {OUTPUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
