"""Adapter for the Anthropic API (default model Claude Haiku 5.5).

One request per paper with structured output for the five fields and low
effort; no sampling parameters (they return 400 on current models). Error
classes map onto summaries.llm: 429, 5xx and connection errors are retried,
another 4xx (such as a 400) or a refusal skips the paper, which stays
"pending" on the site; auth, permission and unknown-model errors stop the run.
"""

import json

import anthropic

from summaries import llm
from summaries.prompting import FIELD_GUIDE, instructions
from summaries.records import AI_FIELDS

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 8000
# Wrong key, permissions or model id: every paper would fail the same way.
FATAL_ERRORS = (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "string", "description": FIELD_GUIDE[name]} for name in AI_FIELDS},
    "required": list(AI_FIELDS),
    "additionalProperties": False,
}


def build_request(paper, language, model=MODEL):
    content = f"Title: {paper.get('title', '')}\n\nAbstract:\n{paper.get('summary', '')}"
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": instructions(language),
        "messages": [{"role": "user", "content": content}],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA},
        },
    }


def make_client(api_key=None):
    """Client for the given key (else ANTHROPIC_API_KEY); retries are handled per paper in summaries.llm."""
    return anthropic.Anthropic(api_key=api_key or None, max_retries=0, timeout=120.0)


def make_call(client, model=MODEL):
    def call(paper, language):
        try:
            response = client.messages.create(**build_request(paper, language, model))
        except FATAL_ERRORS:
            raise
        except anthropic.RateLimitError as error:
            raise llm.Retryable("429: rate limited", llm.retry_after_seconds(error)) from error
        except anthropic.APIStatusError as error:
            if error.status_code >= 500:
                raise llm.Retryable(f"{error.status_code}: {error.message}") from error
            raise llm.Skip(f"{error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise llm.Retryable(f"connection: {error}") from error
        if response.stop_reason == "refusal":
            raise llm.Skip("refusal")
        if response.stop_reason == "max_tokens":
            raise llm.Skip("incomplete output (stop_reason=max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise llm.Skip(f"incomplete output (stop_reason={response.stop_reason})") from error

    return call


def summarize_paper(client, paper, language, **kwargs):
    return llm.summarize_paper(make_call(client), paper, language, **kwargs)


def summarize_all(client, papers, language, **kwargs):
    return llm.summarize_all(make_call(client), papers, language, **kwargs)
