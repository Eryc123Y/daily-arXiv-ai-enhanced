# Claude Code summary mode

The default mode. GitHub Actions publishes the day's papers; a scheduled Claude Code task on Eric's Mac writes the Chinese summaries with Haiku subagents and pushes them to the `data` branch. No API key is involved.

## Commands

All run from the repository root with `uv run python -m summaries ...`:

| Command | What it does |
|---|---|
| `status [--days 4]` | Recent days on the `data` branch with `total`, `done`, `pending`. |
| `prepare --date D [--chunk-size 20]` | Merges any outputs left by an interrupted run, takes the run lock (`.cache/summaries/LOCK`, exit code 3 while another run holds it, expires after 3 hours), and writes `INSTRUCTIONS.md` plus `chunk-NNN.in.txt` for the pending papers. Prints the chunk list as JSON. |
| `merge --date D` | Parses every `chunk-*.out.txt`, keeps complete blocks for papers of that day, merges them into `data/D_AI_enhanced_Chinese.jsonl` and pushes. Existing summaries are never overwritten. Prints `done`, `pending` and any problems. |
| `finish` | Releases the lock and deletes work folders older than 14 days. |
| `handover --date D [--reason ...]` | Usage gate reached: merges finished outputs, then dispatches the `summarize-api` workflow for D if the `ANTHROPIC_API_KEY` secret exists, otherwise pauses. Logs the path. |
| `record --date D --path P` | Appends a line to `logs/summary-runs.jsonl` on the `data` branch. |

Pushes go through git plumbing on a temporary index: the checkout's branch and working tree are untouched, commits carry the `Eryc123Y` noreply identity, and a push that races the Actions job is rebuilt on top of the newer remote state.

## Subagent contract

Each subagent gets the instructions file, one input file and one output path. Input blocks:

```
=== 2610.12345
title: ...
abstract: ...
```

Output blocks (field names in English, content in Chinese, one line each):

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

Before starting and before each wave of subagents the task reads plan usage. At 80% or more of the 5-hour window or of the weekly limit it stops using the subscription and runs `handover`: the remaining papers of the day go to the Actions API job when the secret is set, otherwise the run pauses and a later run resumes. The same subscription runs Eric's research autopilot. A run that ends normally logs `claude-code` with `record`.
