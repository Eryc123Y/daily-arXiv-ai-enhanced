"""API mode: summarise papers in Actions with Claude Haiku 5.5.

One request per paper with structured output for the five fields. 429, 5xx
and connection errors are retried per paper with backoff (the SDK's own
retries are off so attempts are counted here); another 4xx (such as a 400)
or a refusal marks the paper as failed without retry, and it stays
"pending" on the site. Auth, permission and unknown-model errors stop the run.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import anthropic

from summaries.prompting import FIELD_GUIDE, instructions
from summaries.records import AI_FIELDS, clean_ai

MODEL = "claude-haiku-5-5"
# Wrong key, permissions or model id: every paper would fail the same way.
FATAL_ERRORS = (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)
MAX_TOKENS = 8000
MAX_DELAY = 60.0

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "string", "description": FIELD_GUIDE[name]} for name in AI_FIELDS},
    "required": list(AI_FIELDS),
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Outcome:
    paper_id: str
    ai: dict | None
    error: str | None
    attempts: int


def build_request(paper, language):
    content = f"Title: {paper.get('title', '')}\n\nAbstract:\n{paper.get('summary', '')}"
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": instructions(language),
        "messages": [{"role": "user", "content": content}],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA},
        },
    }


def make_client():
    """Client from ANTHROPIC_API_KEY; retries are handled per paper here."""
    return anthropic.Anthropic(max_retries=0, timeout=120.0)


def _retry_after(error):
    try:
        return float(error.response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _read_response(paper_id, response, attempt):
    if response.stop_reason == "refusal":
        return Outcome(paper_id, None, "refusal", attempt)
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        ai = clean_ai(json.loads(text))
    except json.JSONDecodeError:
        ai = None
    if ai is None:
        return Outcome(paper_id, None, f"incomplete output (stop_reason={response.stop_reason})", attempt)
    return Outcome(paper_id, ai, None, attempt)


def summarize_paper(client, paper, language, max_attempts=5, sleep=time.sleep, base_delay=2.0):
    request = build_request(paper, language)
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        delay = min(base_delay * 2 ** (attempt - 1), MAX_DELAY)
        try:
            response = client.messages.create(**request)
        except FATAL_ERRORS:
            raise
        except anthropic.RateLimitError as error:
            last_error = "429: rate limited"
            delay = min(_retry_after(error) or delay, MAX_DELAY)
        except anthropic.APIStatusError as error:
            if error.status_code < 500:
                return Outcome(paper["id"], None, f"{error.status_code}: {error.message}", attempt)
            last_error = f"{error.status_code}: {error.message}"
        except anthropic.APIConnectionError as error:
            last_error = f"connection: {error}"
        else:
            return _read_response(paper["id"], response, attempt)
        if attempt < max_attempts:
            sleep(delay)
    return Outcome(paper["id"], None, f"gave up after {max_attempts} attempts ({last_error})", max_attempts)


def summarize_all(client, papers, language, max_workers=8, **kwargs):
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(summarize_paper, client, p, language, **kwargs) for p in papers]
        return [f.result() for f in futures]
