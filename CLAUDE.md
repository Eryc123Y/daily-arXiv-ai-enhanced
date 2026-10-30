@AGENTS.md

## Claude Code

The scheduled task `daily-arxiv-summaries` runs the interactive form of the summary job with Haiku subagents (Agent tool, model haiku, three at a time) and checks plan usage with `mcp__ccd_session_mgmt__get_usage`; at 80% of the 5-hour or weekly window it runs `uv run python -m summaries handover --date D` instead of continuing. See docs/claude-code-mode.md.
