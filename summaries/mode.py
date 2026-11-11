"""Which component writes the day's summaries, from the SUMMARY_MODE variable.

claude-code (default): Actions only crawls and publishes; a local coding
agent task summarises. api: Actions summarises through the provider chosen
by SUMMARY_PROVIDER (see summaries.providers). A provider that is not ready
(no key, no model) or an unknown value falls back to claude-code with a
warning, so a configuration slip never blocks the crawl.

This instance no longer runs Actions (2026-11-09); the command stays for forks
that run `ingest` and `api` in their own CI.
"""

from dataclasses import dataclass

CLAUDE_CODE = "claude-code"
API = "api"


@dataclass(frozen=True)
class ModeDecision:
    mode: str
    warning: str | None = None


def resolve_mode(requested: str | None, provider_problem: str | None) -> ModeDecision:
    """`provider_problem` is None when the API provider is fully configured."""
    value = (requested or "").strip().lower()
    if value in ("", CLAUDE_CODE):
        return ModeDecision(CLAUDE_CODE)
    if value != API:
        return ModeDecision(
            CLAUDE_CODE,
            f"Unknown SUMMARY_MODE '{(requested or "").strip()}'; using {CLAUDE_CODE}.",
        )
    if provider_problem:
        return ModeDecision(
            CLAUDE_CODE,
            f"SUMMARY_MODE is api but {provider_problem}; "
            f"using {CLAUDE_CODE} (summaries stay pending for the local task).",
        )
    return ModeDecision(API)
