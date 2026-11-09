# A Claude Code scheduled task for the daily pipeline

In the Claude desktop app, create a scheduled task with the cron `20 10,12,16,21 * * 0-5` (local time; the morning run comes about an hour after arXiv's announcement, the midday and afternoon runs catch a late announcement, the evening run resumes anything the morning could not finish) and the prompt below. Replace `<CLONE>` with the absolute path of your clone, `<SITE>` with your page's address and `<DIGEST>` with the folder for the reports (it needs `project-brief.md` with the radar regex and collision levels, and may hold `feedback.md` with standing preferences; see [daily-pipeline.md](daily-pipeline.md)). The task runs only while the app is open; a run that is missed or stopped is picked up by the next one. If the app lets you choose the task's model, Sonnet is enough: the task only runs commands.

Without the digest, steps 1 to 3 alone keep the summaries up to date; or use `uv run python -m summaries run-local --client <claude|codex|antigravity>` from cron or launchd (see README).

```text
Daily arXiv: make sure the day's crawl ran, write the site summaries, then a short Chinese report and one push notification. Site: <SITE>

Repository: <CLONE>. Digest folder: `<DIGEST>` (DIGEST below; write it out in full in commands). Design and measurements: docs/daily-pipeline.md in the repository.

Rules:
- Run every shell command as `cd <CLONE> && <command>` with a 600000 ms timeout. The scripts push to the `data` branch and write in DIGEST themselves.
- Do not edit or commit code, switch branches, or touch other repositories or sessions. Never read, print or ask for an API key.
- Do not read paper data, chunk files or prompts yourself, and keep messages short. Use as few tool calls as you can: every call re-reads this conversation.

Tools: load both with one ToolSearch query "select:mcp__ccd_session_mgmt__get_usage,PushNotification". Gate reached = the "5-hour limit" or the "Weekly · all models" window has percentUsed 80 or more.

Sunday:
1. `uv run python -m summaries missed --dir "DIGEST"; uv run python -m summaries digest-week --dir "DIGEST"`. The first records last week's look-back papers that were in one of our batches in DIGEST/missed.md (if its output has `skipped`, add one line to the final message naming the file and the rows it could not read); the second writes the weekly page. If digest-week's status is not "written", reply with one line and stop.
2. Call get_usage. Unless the gate is reached, start one Agent (subagent_type "general-purpose", model "sonnet", description "arXiv weekly look-back") with this prompt, DIGEST and <today> written out: "Find at most 3 influential older papers for my project radar. Read DIGEST/project-brief.md and take sub-direction ((ISO week number - 1) mod 5) + 1 from its list. Load the alphaXiv discover_papers tool with ToolSearch and call it twice for that sub-direction, prioritize 'historical' and then 'popular'. Skip IDs that appear in DIGEST/project-radar.md or the brief. Judge from abstracts only. Append to DIGEST/digests/<today>.md a section '## 旧文回溯（子方向 N）' with one line per paper: [title](https://arxiv.org/abs/ID) — 中文一句话说明为什么值得读. Append one row per paper to DIGEST/project-radar.md: | <today> | ID | title | 可借鉴（回溯） | 一句话关系 | 视情况阅读 |. Reply with the IDs only."
3. Go to Finish.

Monday to Friday:
1. `[ -z "$(git status --porcelain)" ] && [ "$(git branch --show-current)" = main ] && git pull --ff-only --quiet; uv run python -m summaries ensure-day`. It starts the GitHub crawl when today's papers are missing and waits for it; if Actions refuses (for example disabled on the fork), it crawls arXiv on this Mac and publishes the day itself (`crawled_locally: true`). Note its status and go on whatever it is.
2. Call get_usage and note both numbers. If the gate is reached: run `uv run python -m summaries status --days 4`, then `uv run python -m summaries handover --date D --reason "<5h N%, weekly M%>"` for each date with pending above 0, and go to step 4.
3. `uv run python -m summaries run-local --client claude --parallel 4 --max-chunks 12`. Headless Haiku calls summarise 40 papers each; the command merges, pushes and logs the day. If its JSON has "stopped": "chunk budget reached", call get_usage and run it again unless the gate is reached (three runs at most). Exit code 3: another run holds the lock; go on. If every chunk failed because the claude command itself failed, summarise this time with subagents instead: for each date D with pending papers run `uv run python -m summaries prepare --date D` (`--force` after the first), give each chunk to one Agent (subagent_type "general-purpose", model "haiku", prompt "Read <instructions> and follow it exactly. Input file: <input>. Output file: <output>. Use only the Read and Write tools."), six per message, then `uv run python -m summaries merge --date D` and `uv run python -m summaries record --date D --path claude-code`; finally `uv run python -m summaries finish`.
4. `uv run python -m summaries digest --dir "DIGEST" --wait-summaries`, adding `--final` when the local time is after 18:00. It writes DIGEST/digests/<today>.md with Sonnet from the site data.
   - "written": go to Finish.
   - "exists", "no-new-batch", "summaries-pending" or "written-no-batch": reply with one line and stop, no notification.
   - "error": reply with one line giving the reason and stop; the next run tries again.

Finish: send one PushNotification with the JSON's `push` text. Then reply with the JSON's `report` Markdown unchanged, followed by one line with summaries done/pending per date and usage before and after, and the line "想调整偏好（多看/少看什么、格式）直接回复，我会写进 feedback.md。"

If I reply later in this session with a lasting preference, append `- YYYY-MM-DD: <preference>` to DIGEST/feedback.md and say which line you wrote; answer questions about a single paper without writing anything. Changes to the research project itself belong in DIGEST/project-brief.md, which I maintain myself: tell me instead of editing it.
```
