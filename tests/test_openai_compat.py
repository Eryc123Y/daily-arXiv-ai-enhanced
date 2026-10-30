import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from summaries.llm import Retryable, Skip
from summaries.openai_compat import build_request, make_call

AI = {"tldr": "t", "motivation": "m", "method": "x", "result": "r", "conclusion": "c"}
PAPER = {"id": "2610.00001", "title": "Stereo Video", "summary": "We convert $2$D video to 3D."}
REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def completion(content=None, finish_reason="stop", refusal=None):
    message = SimpleNamespace(content=json.dumps(AI) if content is None else content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def status_error(cls, code, headers=None):
    return cls("error", response=httpx.Response(code, request=REQUEST, headers=headers or {}), body=None)


def call_with(effect, **kwargs):
    client = MagicMock()
    client.chat.completions.create.side_effect = effect if isinstance(effect, Exception) else None
    if not isinstance(effect, Exception):
        client.chat.completions.create.return_value = effect
    return make_call(client, model="some-model", **kwargs), client


def test_request_uses_a_strict_json_schema_and_no_sampling_or_length_params():
    request = build_request(PAPER, "English", model="gpt-x")
    assert request["model"] == "gpt-x"
    fmt = request["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["required"] == ["tldr", "motivation", "method", "result", "conclusion"]
    for absent in ("temperature", "top_p", "max_tokens", "max_completion_tokens", "reasoning_effort"):
        assert absent not in request
    assert request["messages"][0]["role"] == "system" and "English" in request["messages"][0]["content"]
    assert "We convert $2$D video to 3D." in request["messages"][1]["content"]


def test_reasoning_effort_is_sent_only_when_configured():
    assert build_request(PAPER, "English", model="m", reasoning_effort="low")["reasoning_effort"] == "low"


def test_json_object_mode_for_servers_without_json_schema():
    request = build_request(PAPER, "English", model="m", response_format="json_object")
    assert request["response_format"] == {"type": "json_object"}
    assert "JSON object" in request["messages"][0]["content"]
    assert "conclusion" in request["messages"][0]["content"]


def test_success_parses_the_message_content():
    call, client = call_with(completion())
    assert call(PAPER, "English") == AI
    assert client.chat.completions.create.call_args.kwargs["model"] == "some-model"


def test_refusal_truncation_and_content_filter_skip_the_paper():
    for done in (completion(refusal="I can't"), completion(finish_reason="length"), completion(finish_reason="content_filter")):
        call, _ = call_with(done)
        with pytest.raises(Skip):
            call(PAPER, "English")


def test_invalid_json_skips_the_paper():
    call, _ = call_with(completion(content="not json"))
    with pytest.raises(Skip):
        call(PAPER, "English")


def test_rate_limits_server_and_connection_errors_are_retryable():
    call, _ = call_with(status_error(openai.RateLimitError, 429, {"retry-after": "3"}))
    with pytest.raises(Retryable) as error:
        call(PAPER, "English")
    assert error.value.retry_after == 3.0
    for effect in (status_error(openai.InternalServerError, 500), openai.APIConnectionError(request=REQUEST)):
        call, _ = call_with(effect)
        with pytest.raises(Retryable):
            call(PAPER, "English")


def test_bad_requests_skip_but_auth_and_model_errors_stop():
    call, _ = call_with(status_error(openai.BadRequestError, 400))
    with pytest.raises(Skip):
        call(PAPER, "English")
    for cls, code in ((openai.AuthenticationError, 401), (openai.NotFoundError, 404)):
        call, _ = call_with(status_error(cls, code))
        with pytest.raises(cls):
            call(PAPER, "English")


def test_an_empty_base_url_variable_still_reaches_openai(monkeypatch):
    """Actions exports unset variables as empty strings, which the SDK would use as the base URL."""
    from summaries.openai_compat import make_client

    monkeypatch.setenv("OPENAI_BASE_URL", "")
    assert str(make_client("k", None).base_url).startswith("https://api.openai.com/v1")
    assert str(make_client("k", "https://api.deepseek.com/v1").base_url).startswith("https://api.deepseek.com/v1")


def test_exhausted_quota_stops_the_run_instead_of_retrying():
    error = openai.RateLimitError(
        "quota", response=httpx.Response(429, request=REQUEST), body={"code": "insufficient_quota", "message": "quota"}
    )
    call, _ = call_with(error)
    with pytest.raises(openai.RateLimitError):
        call(PAPER, "English")


def test_timeouts_and_conflicts_are_retryable():
    for code in (408, 409):
        call, _ = call_with(status_error(openai.APIStatusError, code))
        with pytest.raises(Retryable):
            call(PAPER, "English")


def test_an_invalid_key_reported_as_400_stops_the_run():
    error = openai.BadRequestError(
        "API key not valid. Please pass a valid API key.", response=httpx.Response(400, request=REQUEST), body=None
    )
    call, _ = call_with(error)
    with pytest.raises(openai.BadRequestError):
        call(PAPER, "English")
