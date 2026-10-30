# daily-arXiv (Eryc123Y)

> [!CAUTION]
> 若您所在法域对学术数据有审查要求，谨慎运行本代码；任何二次分发版本必须履行合规审查（包括但不限于原始论文合规性、AI合规性）义务，否则一切法律后果由下游自行承担。
>
> If your jurisdiction has censorship requirements for academic data, run this code with caution; any secondary distribution version must remove the entrance accessible to China and fulfill the content review obligations, otherwise all legal consequences will be borne by the downstream.

A personal fork of [dw-dengwei/daily-arXiv-ai-enhanced](https://github.com/dw-dengwei/daily-arXiv-ai-enhanced) (Apache-2.0, see [LICENSE](LICENSE)). Page: **https://eryc123y.github.io/daily-arXiv-ai-enhanced/**

Every new paper of the day in cs.CV, cs.AI, cs.LG, cs.CL, stat.ML and cs.GR (new submissions and same-period cross-lists, not replacements), each with a five-part English summary (TL;DR, motivation, method, result, conclusion). Papers matching research-interest keywords or authors are marked and listed first. The default keywords live in [`js/interest-presets.js`](js/interest-presets.js) and can be changed per browser under "Keywords & authors".

## How a day flows

1. **GitHub Actions** ([`run.yml`](.github/workflows/run.yml), 01:30 UTC plus a 07:30 UTC catch-up) reads each category's `/new` listing, drops papers already published in the past week, and commits `data/<date>.jsonl` to the `data` branch. Days without an arXiv announcement (weekends, holidays, late batches) publish nothing and the page keeps the last day.
2. **Summaries** are written to `data/<date>_AI_enhanced_English.jsonl` by one of two modes (below). Until a paper has its summary, the page shows its abstract, says the summary is not written yet, and a progress bar shows how many are ready.
3. **GitHub Pages** serves this branch's static site, which reads both files from the `data` branch.

## Summary modes

Set by the repository variable `SUMMARY_MODE`.

| Mode | Who summarises | Needs |
|---|---|---|
| `claude-code` (default, also when unset) | A scheduled Claude Code task on Eric's Mac, using Haiku subagents | Claude subscription; the Mac awake with the Claude app open |
| `api` | The Actions job, Claude Haiku 5.5 (`claude-haiku-5-5`, effort low, structured output) | Secret `ANTHROPIC_API_KEY` |

Switch to API mode:

```bash
gh secret set ANTHROPIC_API_KEY -R Eryc123Y/daily-arXiv-ai-enhanced
```

```bash
gh variable set SUMMARY_MODE --body api -R Eryc123Y/daily-arXiv-ai-enhanced
```

Switch back with `gh variable set SUMMARY_MODE --body claude-code -R Eryc123Y/daily-arXiv-ai-enhanced`. If `api` is set without the secret, the job warns and falls back to `claude-code`. In API mode the local task finds nothing pending and only fills papers the API skipped (429/5xx are retried; a 400 or a refusal leaves the paper pending); it can also be paused in the Claude app.

### The local task (claude-code mode)

Scheduled task `daily-arxiv-summaries`, daily at 10:30, 16:30 and 21:30 local time (MYT), so it starts about an hour after the morning crawl and has two later chances to resume. Each run:

1. checks plan usage before starting and before every wave of subagents (Eric's research autopilot shares the subscription; see the fallback below);
2. `uv run python -m summaries status` to find recent days with pending papers;
3. `uv run python -m summaries prepare --date D` writes chunks of 20 pending papers to `.cache/summaries/D/`;
4. Haiku subagents, three at a time, each turn one chunk into a plain-text block file;
5. `uv run python -m summaries merge --date D` validates the blocks, merges them into the day's summary file and pushes it to the `data` branch, after every few chunks;
6. `uv run python -m summaries finish` releases the run's lock.

Progress is committed as it goes and finished papers are skipped, so a run that stops (usage gate, app closed) continues where it left off on the next run. Details: [docs/claude-code-mode.md](docs/claude-code-mode.md).

### Fallback at the usage gate

When the 5-hour window or the weekly limit reaches **80%**, the task stops using the subscription and runs `uv run python -m summaries handover --date D`:

- it merges and publishes what the subagents finished;
- if the repository has an `ANTHROPIC_API_KEY` secret (only its name is checked, with `gh secret list`), it dispatches [`summarize-api.yml`](.github/workflows/summarize-api.yml) for that date. That Actions job summarises the remaining papers with Claude Haiku 5.5 through the same `api` code path, so the day still ends complete;
- without the secret it pauses: the rest of the day stays "summary pending" on the page and the next scheduled run resumes on the subscription.

Every outcome is appended to `logs/summary-runs.jsonl` on the `data` branch (`date`, `path` = `claude-code` / `api` / `api-fallback` / `paused-no-key`, `total`, `done`, `pending`, time, reason). The key lives only in the GitHub secret, never on the Mac.

## Data branch

- `data/<date>.jsonl`: one paper per line (`id`, `title`, `authors`, `categories` with the primary first, `summary` = abstract, `comment`, `abs`, `pdf`, optional `code_url`).
- `data/<date>_AI_enhanced_English.jsonl` (`LANGUAGE` variable; older days also have upstream's `_Chinese` files): the same records plus `AI` = `{tldr, motivation, method, result, conclusion}`, only for papers whose summary is complete.
- `assets/file-list.txt`: every jsonl file on the branch, rebuilt on each commit.
- `logs/summary-runs.jsonl`: which summary path ran for each day.

Raw URL pattern: `https://raw.githubusercontent.com/Eryc123Y/daily-arXiv-ai-enhanced/data/data/<date>.jsonl`.

## Development

```bash
uv sync && uv run pytest -q
```

```bash
node --test tests/js/*.test.js
```

Code map: `daily_arxiv/` (Scrapy spider for the listings), `summaries/` (data-branch publishing, both summary modes, CLI), `index.html`, `css/site.css` and `js/{app,render,paper-data,interest-presets}.js` (the reading page; `statistic.html` is upstream's keyword-trends page). `ai/enhance.py` is upstream's OpenAI-compatible summariser, kept but not used by the workflow.

## Changes from upstream

- Metadata comes from the listing page itself, not one arXiv API call per paper; cross-lists are included.
- Deduplication against the past week of the `data` branch, so weekend reruns do not republish Friday.
- The workflow no longer commits to `main`, and has the `contents: write` permission it needs.
- `assets/file-list.txt` lists every day, which fixes the date-range view (upstream #136).
- Summaries are produced by Claude (two modes above); papers without one are shown as pending instead of being dropped.
- Keyword matching uses whole words over title, abstract and TL;DR.
- A new single-page reading layout (date, paper count, interest matches first, expandable summaries, light and dark, phone width); keyword and author settings are a dialog on the same page.
