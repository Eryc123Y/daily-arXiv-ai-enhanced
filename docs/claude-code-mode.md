# Claude Code summary mode

The default mode. A scheduled Claude Code task on Eric's Mac crawls and publishes the day's papers, refreshes the Hugging Face upvotes, writes the English summaries with headless Haiku calls, pushes them to the `data` branch and then writes the short Chinese report. No API key is involved. Why it works this way, with measurements: [daily-pipeline.md](daily-pipeline.md); the task's prompt: [claude-code-task.md](claude-code-task.md).

## Commands

All run from the repository root with `uv run python -m summaries ...`:

| Command | What it does |
|---|---|
| `ensure-day [--date D]` | Crawls today's `/new` listings on this machine when the day is not on the `data` branch yet, and first backfills weekdays missed since the newest published day from the `/recent` listing (last five announcements; abstracts from the arXiv API). Prints `status` (`present`, `missing` = nothing new yet, `error`, `weekend`) and, when there were missed days, `backfilled` (day: papers added), `gap` (days too old for the listing) and `backfill_error`. A day that holds only feed papers does not count as crawled. On today's run, any day of the week, it then runs the feed (below) and prints `feed`: `"skipped"` when `FEED_COMMAND` is unset, else an object with `status` (`published`, `nothing new`, `error`), `since`, `received`, `invalid` (lines dropped), `off_topic` (papers of `match: topics` venues dropped by the topic filter, per venue), `duplicates`, `added`, `abstracts_added` (papers of the last four days, published without an abstract, that gained one), `deferred`, `no_abstract` and, on error, `reason`. A failed feed leaves the exit code and the arXiv part alone. |
| `hf-signals --days 7` | Hugging Face Daily Papers upvotes for the last week's days, as `data/<date>_hf.json`. |
| `run-local --client claude [--parallel 4] [--max-chunks N]` | The summaries: 40 pending papers per headless `claude -p --model haiku --tools Read,Write --strict-mcp-config` call, merged and pushed every few chunks, logged as `local-claude`. Takes the same lock as `prepare`. |
| `digest --dir DIGEST [--wait-summaries] [--final]` | The day's Chinese report from the site data (see below). |
| `digest-week --dir DIGEST` | Sunday: the week's reports on one page, with no model call. |
| `status [--days 4]` | Recent days on the `data` branch with `total`, `done`, `pending`, and `no_abstract` when a day has feed papers whose abstract is not in this machine's work folder (listed without a summary, never pending). |
| `prepare --date D [--chunk-size 20]` | Merges any outputs left by an interrupted run, takes the run lock (`.cache/summaries/LOCK`, exit code 3 while another run holds it, expires after 3 hours), and writes `INSTRUCTIONS.md` plus `chunk-NNN.in.txt` for the pending papers. Prints the chunk list as JSON. |
| `merge --date D` | Parses every `chunk-*.out.txt`, keeps complete blocks for papers of that day, merges them into `data/D_AI_enhanced_English.jsonl` and pushes. Existing summaries are never overwritten. Prints `done`, `pending` and any problems. |
| `finish` | Releases the lock and deletes work folders older than 14 days. |
| `handover --date D [--reason ...]` | Usage gate reached: merges finished outputs, then summarises the rest of D through the API on this machine if a provider is ready in the environment (key variable, model where required), otherwise pauses and logs why. |
| `record --date D --path P` | Appends a line to `logs/summary-runs.jsonl` on the `data` branch. |

The feed (spec [S1](specs/s1-sources-beyond-arxiv.md)): `FEED_COMMAND` is a JSON argv list (LitScout's `watch` once it exists); `ensure-day` appends `--since <cursor, or four days ago if earlier> --venues summaries/watchlist.json --kinds journal,conference` (LitScout reads only journals without `--kinds`; both kinds share the one cursor) and reads one paper per line (`FeedLine` in `summaries/shapes.py`). Only `openalex`, `crossref`, `openreview`, `acl-anthology`, `pmlr`, `datacite` and `jmlr` are accepted as `source`; a paper with no DOI, arXiv ID or OpenReview id (PMLR, JMLR, some ACL Anthology papers) gets the id `url:<url>`. A venue marked `match: "topics"` in the watch list (the large conferences and journals) keeps only papers whose title or abstract matches an interest keyword of `js/interest-presets.js`, with the page's matching (`summaries/interests.py`); the rest are dropped before anything else and counted in `off_topic`. Papers already on the `data` branch in the last 60 days (by id, DOI, or title and first author) are dropped; the rest go into today's `data/<today>.jsonl` without their abstracts, which stay in `.cache/summaries/abstracts.jsonl` for `prepare`, `run-local` and `handover`. The cursor `assets/feed-cursor.json` moves in the same commit. At most `FEED_MAX_PER_RUN` (default 150) new papers go into one day, in the order received; when more arrive (proceedings come as one batch), the rest are reported as `deferred`, the cursor stays, and the next runs take them. Each published feed record says `has_abstract`, so the page can tell a summary still to come from one that never will. Asking again for the last four days catches abstracts that come late (Crossref lists a fresh IEEE paper the day it is registered, OpenAlex adds the abstract a day or so later): a paper published in those days without an abstract that comes back with one keeps its place and day, gets `has_abstract: true` there, its abstract goes to the local file, and it is pending on that day for `status --days 4` and `run-local`. It is not published again, not counted against `FEED_MAX_PER_RUN`, and not in today's report. Older papers stay as they are.

Pushes go through git plumbing on a temporary index: the checkout's branch and working tree are untouched, commits carry the `Eryc123Y` noreply identity, and a push that races another run is rebuilt on top of the newer remote state.

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
