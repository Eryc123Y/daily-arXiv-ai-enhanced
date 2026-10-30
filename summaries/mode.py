"""Which component writes the day's summaries, from the SUMMARY_MODE variable.

claude-code (default): Actions only crawls and publishes; a local Claude Code
task summarises. api: Actions summarises with the Anthropic API, which needs
the ANTHROPIC_API_KEY secret. A missing key or an unknown value falls back to
claude-code with a warning, so a configuration slip never blocks the crawl.
"""

from dataclasses import dataclass

CLAUDE_CODE = "claude-code"
API = "api"


@dataclass(frozen=True)
class ModeDecision:
    mode: str
    warning: str | None = None


def resolve_mode(requested, api_key_present):
    value = (requested or "").strip().lower()
    if value in ("", CLAUDE_CODE):
        return ModeDecision(CLAUDE_CODE)
    if value != API:
        return ModeDecision(
            CLAUDE_CODE,
            f"Unknown SUMMARY_MODE '{requested.strip()}'; using {CLAUDE_CODE}.",
        )
    if not api_key_present:
        return ModeDecision(
            CLAUDE_CODE,
            "SUMMARY_MODE is api but the ANTHROPIC_API_KEY secret is not set; "
            f"using {CLAUDE_CODE} (summaries stay pending for the local task).",
        )
    return ModeDecision(API)
