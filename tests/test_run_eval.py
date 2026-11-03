"""Every evaluation is local and free: the command `run_eval` builds turns
off verifiers' three paid defaults, as verifiers itself reads it."""

import json
import subprocess
from pathlib import Path

import pytest

from analyst_env.backbone import NotLocalError
from analyst_env.run_eval import EvalRun, eval_command, eval_environment

LOCAL_MODEL_URL = "http://127.0.0.1:11434/v1"


def _resolved_config(tmp_path: Path) -> dict[str, object]:
    """The run's config as verifiers resolves it (`--dry-run` writes it, runs nothing)."""
    run = EvalRun("qwen3:1.7b", LOCAL_MODEL_URL, "dry", tmp_path)
    command = [*eval_command(run), "--dry-run"]
    subprocess.run(command, env=eval_environment(), check=True, capture_output=True)
    return json.loads((tmp_path / "dry" / "configs" / "resolved" / "eval.json").read_text())


def test_verifiers_reads_our_command_as_no_upload(tmp_path: Path) -> None:
    assert _resolved_config(tmp_path)["push"] is False


def test_verifiers_reads_our_command_as_a_local_agent(tmp_path: Path) -> None:
    agent = _resolved_config(tmp_path)["env"]["agent"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert agent["runtime"] == {"type": "subprocess"}
    assert agent["harness"]["id"] == "null"


def test_verifiers_reads_our_command_as_a_local_model(tmp_path: Path) -> None:
    client = _resolved_config(tmp_path)["client"]
    assert client["base_url"] == LOCAL_MODEL_URL  # pyright: ignore[reportIndexIssue]
    assert client["api_key_var"] != "PRIME_API_KEY"  # pyright: ignore[reportIndexIssue]


@pytest.mark.parametrize("url", ["https://api.pinference.ai/api/v1", "http://10.0.0.5:11434/v1"])
def test_a_model_server_off_this_machine_is_refused(url: str) -> None:
    with pytest.raises(NotLocalError):
        eval_command(EvalRun("any", url, "run"))


def test_the_run_never_sees_prime_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIME_API_KEY", "a-key")
    monkeypatch.setenv("PRIME_TEAM_ID", "a-team")
    environment = eval_environment()
    assert "PRIME_API_KEY" not in environment
    assert "PRIME_TEAM_ID" not in environment


def test_the_prime_runs_sdk_is_switched_off() -> None:
    assert eval_environment()["PRIME_RUNS_MODE"] == "disabled"
