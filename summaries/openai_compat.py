"""Adapter for OpenAI-style Chat Completions APIs.

Covers OpenAI itself, Gemini through its OpenAI-compatible endpoint, and any
other compatible server (DeepSeek, OpenRouter, vLLM, Ollama) via a base URL.
Structured output uses a strict JSON schema; servers that only know JSON
mode can be switched to `json_object`. No sampling or length parameters are
sent, since reasoning models reject them.
"""

import json

import openai

from summaries.llm import Retryable, Skip, retry_after_seconds
from summaries.prompting import FIELD_GUIDE, instructions
from summaries.records import AI_FIELDS

SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "string", "description": FIELD_GUIDE[name]} for name in AI_FIELDS},
    "required": list(AI_FIELDS),
    "additionalProperties": False,
}
FATAL_ERRORS = (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError)
OPENAI_URL = "https://api.openai.com/v1"
RETRY_STATUSES = (408, 409)


def build_request(paper, language, model, response_format="json_schema", reasoning_effort=None):
    system = instructions(language)
    if response_format == "json_object":
        fmt = {"type": "json_object"}
        system += f"\n\nReply with one JSON object with exactly these string keys: {', '.join(AI_FIELDS)}."
    else:
        fmt = {"type": "json_schema", "json_schema": {"name": "paper_summary", "strict": True, "schema": SCHEMA}}
    request = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Title: {paper.get('title', '')}\n\nAbstract:\n{paper.get('summary', '')}"},
        ],
        "response_format": fmt,
    }
    if reasoning_effort:
        request["reasoning_effort"] = reasoning_effort
    return request


def make_client(api_key, base_url=None):
    """Client for one provider; retries are handled per paper in summaries.llm.

    The base URL is always explicit: left as None, the SDK would read
    OPENAI_BASE_URL itself, which Actions sets to "" for an unset variable.
    """
    return openai.OpenAI(api_key=api_key, base_url=base_url or OPENAI_URL, max_retries=0, timeout=120.0)


def _is_fatal(error):
    """Errors every later paper would hit too: no quota left, or a bad key reported as 400."""
    if getattr(error, "code", None) == "insufficient_quota":
        return True
    return error.status_code == 400 and "api key" in str(error.message).lower()


def make_call(client, model, response_format="json_schema", reasoning_effort=None):
    def call(paper, language):
        request = build_request(paper, language, model, response_format, reasoning_effort)
        try:
            response = client.chat.completions.create(**request)
        except FATAL_ERRORS:
            raise
        except openai.APIStatusError as error:
            if _is_fatal(error):
                raise
            if error.status_code == 429:
                raise Retryable("429: rate limited", retry_after_seconds(error)) from error
            if error.status_code >= 500 or error.status_code in RETRY_STATUSES:
                raise Retryable(f"{error.status_code}: {error.message}") from error
            raise Skip(f"{error.status_code}: {error.message}") from error
        except openai.APIConnectionError as error:
            raise Retryable(f"connection: {error}") from error
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise Skip("refusal")
        if choice.finish_reason in ("length", "content_filter"):
            raise Skip(f"incomplete output (finish_reason={choice.finish_reason})")
        try:
            return json.loads(choice.message.content or "")
        except json.JSONDecodeError as error:
            raise Skip("output was not valid JSON") from error

    return call
