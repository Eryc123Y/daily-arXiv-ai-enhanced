import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest

from summaries.anthropic_api import MODEL, build_request, summarize_all, summarize_paper

AI = {
    "tldr": "总结",
    "motivation": "动机",
    "method": "方法",
    "result": "结果",
    "conclusion": "结论",
}
PAPER = {"id": "2610.00001", "title": "Stereo Video", "summary": "We convert $2$D video to 3D."}
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def message(payload=AI, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False)),
        ],
    )


def status_error(cls, code, headers=None):
    return cls("error", response=httpx2.Response(code, request=REQUEST, headers=headers or {}), body=None)


def client_returning(*effects):
    client = MagicMock()
    client.messages.create.side_effect = list(effects)
    return client


def test_request_uses_haiku_low_effort_and_a_strict_schema_without_sampling_params():
    request = build_request(PAPER, "Chinese")

    assert request["model"] == MODEL == "claude-haiku-5-5"
    assert request["output_config"]["effort"] == "low"
    schema = request["output_config"]["format"]["schema"]
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert schema["required"] == ["tldr", "motivation", "method", "result", "conclusion"]
    assert schema["additionalProperties"] is False
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in request
    assert "We convert $2$D video to 3D." in request["messages"][0]["content"]
    assert "Chinese" in request["system"]


def test_success_reads_the_text_block_after_thinking():
    outcome = summarize_paper(client_returning(message()), PAPER, "Chinese", sleep=lambda s: None)
    assert outcome.ai == AI
    assert outcome.error is None


def test_rate_limit_is_retried_honouring_retry_after():
    sleeps = []
    client = client_returning(status_error(anthropic.RateLimitError, 429, {"retry-after": "7"}), message())

    outcome = summarize_paper(client, PAPER, "Chinese", sleep=sleeps.append)

    assert outcome.ai == AI
    assert outcome.attempts == 2
    assert sleeps == [7.0]


def test_server_errors_and_connection_errors_are_retried_with_backoff():
    sleeps = []
    client = client_returning(
        status_error(anthropic.InternalServerError, 500),
        status_error(anthropic.APIStatusError, 529),
        anthropic.APIConnectionError(request=REQUEST),
        message(),
    )

    outcome = summarize_paper(client, PAPER, "Chinese", sleep=sleeps.append, base_delay=1.0)

    assert outcome.ai == AI
    assert sleeps == [1.0, 2.0, 4.0]


def test_retries_give_up_and_mark_the_paper_instead_of_raising():
    client = client_returning(*[status_error(anthropic.InternalServerError, 503)] * 3)
    outcome = summarize_paper(client, PAPER, "Chinese", max_attempts=3, sleep=lambda s: None)
    assert outcome.ai is None
    assert "503" in outcome.error
    assert client.messages.create.call_count == 3


def test_bad_request_is_skipped_and_marked_without_retry():
    client = client_returning(status_error(anthropic.BadRequestError, 400))
    outcome = summarize_paper(client, PAPER, "Chinese", sleep=lambda s: None)
    assert outcome.ai is None
    assert outcome.error.startswith("400")
    assert client.messages.create.call_count == 1


def test_refusal_and_truncated_output_are_marked_without_retry():
    refused = summarize_paper(
        client_returning(message(stop_reason="refusal")), PAPER, "Chinese", sleep=lambda s: None
    )
    truncated = summarize_paper(
        client_returning(message({"tldr": "x"}, stop_reason="max_tokens")), PAPER, "Chinese", sleep=lambda s: None
    )
    assert refused.ai is None and "refusal" in refused.error
    assert truncated.ai is None and "max_tokens" in truncated.error


def test_authentication_errors_stop_the_run():
    client = client_returning(status_error(anthropic.AuthenticationError, 401))
    with pytest.raises(anthropic.AuthenticationError):
        summarize_paper(client, PAPER, "Chinese", sleep=lambda s: None)


def test_summarize_all_keeps_input_order():
    papers = [{**PAPER, "id": str(i)} for i in range(5)]
    client = MagicMock()
    client.messages.create.side_effect = lambda **kwargs: message()

    outcomes = summarize_all(client, papers, "Chinese", max_workers=3, sleep=lambda s: None)

    assert [o.paper_id for o in outcomes] == ["0", "1", "2", "3", "4"]
    assert all(o.ai == AI for o in outcomes)


def test_other_client_errors_are_marked_per_paper_but_auth_and_model_errors_stop():
    unprocessable = summarize_paper(
        client_returning(status_error(anthropic.UnprocessableEntityError, 422)), PAPER, "Chinese", sleep=lambda s: None
    )
    assert unprocessable.ai is None and unprocessable.error.startswith("422")
    with pytest.raises(anthropic.NotFoundError):
        summarize_paper(client_returning(status_error(anthropic.NotFoundError, 404)), PAPER, "Chinese", sleep=lambda s: None)


def test_retry_after_is_capped():
    sleeps = []
    client = client_returning(status_error(anthropic.RateLimitError, 429, {"retry-after": "900"}), message())
    summarize_paper(client, PAPER, "Chinese", sleep=sleeps.append)
    assert sleeps == [60.0]
