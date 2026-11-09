"""The scripted model server reports a policy's error instead of hanging
up: a dropped connection reaches the test only as "Server disconnected"."""

import json
import urllib.error
import urllib.request

import pytest

from tests.scripted.model_server import MODEL_PREFIX, ScriptedModel, serve
from tests.scripted.policies import KnownAnswers


def test_a_policy_error_is_answered_with_a_500_that_names_it() -> None:
    # No tasks, so no question matches and the policy can't be played.
    model = ScriptedModel([], KnownAnswers(copy_a={}, stock={}))
    body = {"model": MODEL_PREFIX + "honest", "messages": [{"role": "user", "content": "Q?"}]}
    with serve(model) as base_url:
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
    assert raised.value.code == 500
    assert raised.value.read().decode().startswith("ValueError: 0 tasks match the question")
