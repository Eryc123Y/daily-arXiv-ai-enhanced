"""Provider-neutral summarising loop used by every API adapter.

An adapter is a function `call(paper, language) -> dict` that returns the
five summary fields, or raises:
  Retryable  rate limits, server errors, network trouble (retried with backoff)
  Skip       this paper cannot be summarised (refusal, bad request, truncation);
             it stays "pending" on the site
Anything else (a wrong key or model name) stops the run.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from summaries.records import clean_ai

MAX_DELAY = 60.0


class Retryable(Exception):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


class Skip(Exception):
    pass


@dataclass(frozen=True)
class Outcome:
    paper_id: str
    ai: dict | None
    error: str | None
    attempts: int


def summarize_paper(call, paper, language, max_attempts=5, sleep=time.sleep, base_delay=2.0):
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            fields = call(paper, language)
        except Skip as error:
            return Outcome(paper["id"], None, str(error), attempt)
        except Retryable as error:
            last_error = str(error)
            if attempt < max_attempts:
                backoff = base_delay * 2 ** (attempt - 1)
                sleep(min(error.retry_after or backoff, MAX_DELAY))
            continue
        ai = clean_ai(fields)
        if ai is None:
            return Outcome(paper["id"], None, "incomplete output", attempt)
        return Outcome(paper["id"], ai, None, attempt)
    return Outcome(paper["id"], None, f"gave up after {max_attempts} attempts ({last_error})", max_attempts)


def summarize_all(call, papers, language, max_workers=8, **kwargs):
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(summarize_paper, call, p, language, **kwargs) for p in papers]
        return [f.result() for f in futures]


def retry_after_seconds(error):
    """The Retry-After header of an SDK status error, if it is a number."""
    try:
        return float(error.response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None
