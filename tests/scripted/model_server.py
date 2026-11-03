"""A stand-in for a model server: speaks just enough of the OpenAI chat
completions API for verifiers, and answers with a scripted policy's tool
calls, so policies play through the real `vf-eval` at no cost.

The policy comes from the request's model name (`scripted/<policy>`); the
task from the question in the user message. Turn n gets the policy's n-th
tool call; after the last, a plain reply ends the rollout."""

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from analyst_env.tasks import Task
from tests.scripted.policies import EXPECTED_REWARD, KnownAnswers, ToolCall

MODEL_PREFIX = "scripted/"
FINAL_REPLY = "Done."


class ScriptedModel:
    def __init__(self, tasks: list[Task], known: KnownAnswers) -> None:
        self._tasks = tasks
        self._known = known

    def reply(self, body: dict[str, Any]) -> dict[str, Any]:
        policy, _ = EXPECTED_REWARD[str(body["model"]).removeprefix(MODEL_PREFIX)]
        messages: list[dict[str, Any]] = body["messages"]
        turns = policy(self._task_for(messages), self._known)
        turn = sum(1 for message in messages if message["role"] == "assistant")
        message = _tool_call_message(turn, turns[turn]) if turn < len(turns) else None
        return _completion(str(body["model"]), message)

    def _task_for(self, messages: list[dict[str, Any]]) -> Task:
        question = next(_text(message) for message in messages if message["role"] == "user")
        matches = [task for task in self._tasks if task.prompt in question]
        if len(matches) != 1:
            raise ValueError(f"{len(matches)} tasks match the question {question[:80]!r}")
        return matches[0]


def _text(message: dict[str, Any]) -> str:
    content = message.get("content") or ""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content)


def _tool_call_message(turn: int, calls: list[ToolCall]) -> dict[str, Any]:
    tool_calls = [
        {
            "id": f"call_{turn}_{position}",
            "type": "function",
            "function": {"name": call.tool, "arguments": json.dumps(call.arguments)},
        }
        for position, call in enumerate(calls)
    ]
    return {"role": "assistant", "content": None, "tool_calls": tool_calls}


def _completion(model: str, message: dict[str, Any] | None) -> dict[str, Any]:
    finish_reason = "tool_calls" if message else "stop"
    if message is None:
        message = {"role": "assistant", "content": FINAL_REPLY}
    choice = {"index": 0, "message": message, "finish_reason": finish_reason}
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    return {
        "id": "scripted",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [choice],
        "usage": usage,
    }


def _stream_events(completion: dict[str, Any]) -> list[bytes]:
    """The same completion as server-sent events, the way the agent's
    harness asks for it: the message, the finish reason, then the usage."""
    choice = completion["choices"][0]
    header: dict[str, Any] = {key: completion[key] for key in ("id", "model", "created")}
    header["object"] = "chat.completion.chunk"
    message_delta = {"index": 0, "delta": choice["message"], "finish_reason": None}
    for tool_call_index, tool_call in enumerate(choice["message"].get("tool_calls") or []):
        tool_call["index"] = tool_call_index
    finish: dict[str, Any] = {"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}
    chunks: list[dict[str, Any]] = [
        {**header, "choices": [message_delta]},
        {**header, "choices": [finish]},
        {**header, "choices": [], "usage": completion["usage"]},
    ]
    events = [f"data: {json.dumps(chunk)}\n\n".encode() for chunk in chunks]
    return [*events, b"data: [DONE]\n\n"]


@contextmanager
def serve(model: ScriptedModel) -> Generator[str]:
    """Serves `model` on a free local port; yields its base URL."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the name http.server calls
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            completion = model.reply(body)
            if body.get("stream"):
                payload = b"".join(_stream_events(completion))
                content_type = "text/event-stream"
            else:
                payload = json.dumps(completion).encode()
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
