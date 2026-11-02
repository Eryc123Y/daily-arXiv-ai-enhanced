@AGENTS.md

## Claude Code

The scheduled task `daily-arxiv-summaries` runs `ensure-day`, then the summaries through `run-local --client claude` (headless Haiku; Haiku subagents only as a fallback), then `digest` for the Chinese report, and checks plan usage with `mcp__ccd_session_mgmt__get_usage`; at 80% of the 5-hour or weekly window it runs `uv run python -m summaries handover --date D` instead of continuing. Prompt: docs/claude-code-task.md; design: docs/daily-pipeline.md.
