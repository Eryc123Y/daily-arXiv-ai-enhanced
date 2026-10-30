# A Claude Code scheduled task for the summaries

In the Claude desktop app, create a scheduled task (for example daily at 10:30, 16:30 and 21:30 local time, after the 01:30 UTC crawl) with the prompt below. Replace `<CLONE>` with the absolute path of your clone. The task runs only while the app is open; a run that is missed or stopped is picked up by the next one.

```text
Write the five-part summaries for the arXiv papers on my daily arXiv page that still lack one, through the repository's own scripts.

Rules:
- Run every shell command as `cd <CLONE> && <command>`. The scripts commit and push to the `data` branch themselves.
- Do not edit or commit code, do not switch branches and do not touch other repositories. Never read, print or ask for an API key.
- Keep your own messages short. Never read chunk input or output files yourself; only the subagents do.

Usage gate: load the usage tool with ToolSearch query "select:mcp__ccd_session_mgmt__get_usage". "Gate reached" means the "5-hour limit" or the "Weekly · all models" window has percentUsed 80 or more.

Steps:
1. If `git status --porcelain` prints nothing and `git branch --show-current` is main, run `git pull --ff-only --quiet`.
2. Run `uv run python -m summaries status --days 4`. Work on the dates whose `pending` is above 0, newest first. If there are none, reply "nothing pending" and stop.
3. Call get_usage. If the gate is reached, run `uv run python -m summaries handover --date D --reason "<5h N%, weekly M%>"` for each pending date, reply with the paths it reported, and stop.
4. For each pending date D:
   a. Run `uv run python -m summaries prepare --date D` (add `--force` for every prepare after the first in this run). Exit code 3 on the first prepare means another run holds the lock: reply "locked" and stop. The JSON lists `chunks` (input, output, papers) and the `instructions` file.
   b. Process the chunks in waves of at most 3: one message with one Agent call per chunk, subagent_type "general-purpose", model "haiku", prompt "Read <instructions> and follow it exactly. Input file: <input>. Output file: <output>. Use only the Read and Write tools." Wait for the whole wave before the next.
   c. Before every wave after the first, call get_usage; if the gate is reached, run handover for D and any later pending dates, run `uv run python -m summaries finish`, reply with the paths, and stop.
   d. Run `uv run python -m summaries merge --date D` after every third wave and after the last.
   e. If pending is still above 0 after the last merge, do one more round for D, once only.
   f. Run `uv run python -m summaries record --date D --path claude-code`.
5. Run `uv run python -m summaries finish`.
6. Reply with one short paragraph: per date total, done and pending; how many subagents ran; usage before and after.
```

Without Claude Code, use `uv run python -m summaries run-local --client <claude|codex|antigravity>` from cron or launchd instead (see README).
