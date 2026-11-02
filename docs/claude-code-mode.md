# Claude Code summary mode

The default mode. GitHub Actions publishes the day's papers; a scheduled Claude Code task on Eric's Mac writes the English summaries with headless Haiku calls, pushes them to the `data` branch and then writes the short Chinese report. No API key is involved. Why it works this way, with measurements: [daily-pipeline.md](daily-pipeline.md); the task's prompt: [claude-code-task.md](claude-code-task.md).

## Commands

All run from the repository root with `uv run python -m summaries ...`:

| Command | What it does |
|---|---|
| `ensure-day [--date D] [--wait 480]` | On a weekday whose papers are not on the `data` branch yet, starts the `run.yml` crawl (unless one is running) and waits for it. Prints `present`, `missing` (the crawl found nothing new), `crawl-failed`, `waiting` (still running) or `weekend`. |
| `run-local --client claude [--parallel 4] [--max-chunks N]` | The summaries: 40 pending papers per headless `claude -p --model haiku --tools Read,Write --strict-mcp-config` call, merged and pushed every few chunks, logged as `local-claude`. Takes the same lock as `prepare`. |
| `digest --dir DIGEST [--wait-summaries] [--final]` | The day's Chinese report from the site data (see below). |
| `digest-week --dir DIGEST` | Sunday: the week's reports on one page, with no model call. |
| `status [--days 4]` | Recent days on the `data` branch with `total`, `done`, `pending`. |
| `prepare --date D [--chunk-size 20]` | Merges any outputs left by an interrupted run, takes the run lock (`.cache/summaries/LOCK`, exit code 3 while another run holds it, expires after 3 hours), and writes `INSTRUCTIONS.md` plus `chunk-NNN.in.txt` for the pending papers. Prints the chunk list as JSON. |
| `merge --date D` | Parses every `chunk-*.out.txt`, keeps complete blocks for papers of that day, merges them into `data/D_AI_enhanced_English.jsonl` and pushes. Existing summaries are never overwritten. Prints `done`, `pending` and any problems. |
| `finish` | Releases the lock and deletes work folders older than 14 days. |
| `handover --date D [--reason ...]` | Usage gate reached: merges finished outputs, then dispatches the `summarize-api` workflow for D if the configured API provider is ready (key secret by name, model where required), otherwise pauses and logs why. |
| `record --date D --path P` | Appends a line to `logs/summary-runs.jsonl` on the `data` branch. |

Pushes go through git plumbing on a temporary index: the checkout's branch and working tree are untouched, commits carry the `Eryc123Y` noreply identity, and a push that races the Actions job is rebuilt on top of the newer remote state.

## The report (`digest`)

1. Code reads the newest day from the `data` branch and builds the candidates: the reading page's topic keywords (`summaries/interests.py`, the same matching as `js/paper-data.js`), the radar regex from `DIGEST/project-brief.md`, and every other paper's title and TL;DR. Papers already in `project-radar.md` or the brief are left out.
2. One headless Sonnet call (`claude -p --model sonnet --tools "" --strict-mcp-config`, prompt on stdin, prompt caching off) answers with plain lines: `topic | <topic> | <id> | <gist>`, `radar | <高|中|可借鉴> | <id> | <reason> | <check|->`, `other | <id> | <gist>`, `note | <line>`.
3. For at most two radar papers marked `check`, code downloads the PDF, keeps the main body (`pdftotext`, cut at the references) and a second call regrades them; without a PDF or an answer the abstract grade stays, shown as 仅摘要.
4. Code writes the radar rows to `project-radar.md`, the report to `digests/<today>.md`, and last the ledger entry `## <today>（网站数据 <day>）`, which marks the day as reported. It prints JSON with `status`, `report` and a `push` line under 200 characters.

`--wait-summaries` returns `summaries-pending` while under 95% of the day is summarised; `--final` (the evening run) writes regardless, and on a day without a new batch writes a two-line note. Prompts and answers are kept in `.cache/digest/<day>/`; `picks.json` there feeds `digest-week`.

## Subagent contract

The fallback when the headless `claude` command fails: the task gives each chunk to a subagent instead. Each subagent gets the instructions file, one input file and one output path. Input blocks:

```
=== 2610.12345
title: ...
abstract: ...
```

Output blocks (field names in English, content in English, one line each):

```
=== 2610.12345
tldr: ...
motivation: ...
method: ...
result: ...
conclusion: ...
```

Plain text instead of JSON because abstracts are full of LaTeX backslashes and quotes that a model escapes unreliably. A block missing a field is reported and the paper stays pending for the next pass.

## Usage gate

Before the summaries (and before each further `run-local` run) the task reads plan usage. At 80% or more of the 5-hour window or of the weekly limit it stops using the subscription and runs `handover`: the remaining papers of the day go to the Actions API job when the secret is set, otherwise the run pauses and a later run resumes. The same subscription runs Eric's research autopilot. A run that ends normally is logged as `local-claude` by `run-local` (or `claude-code` on the subagent fallback).
