# Daily arXiv

> [!CAUTION]
> 若您所在法域对学术数据有审查要求，谨慎运行本代码；任何二次分发版本必须履行合规审查（包括但不限于原始论文合规性、AI合规性）义务，否则一切法律后果由下游自行承担。
>
> If your jurisdiction has censorship requirements for academic data, run this code with caution; any secondary distribution version must remove the entrance accessible to China and fulfill the content review obligations, otherwise all legal consequences will be borne by the downstream.

A daily arXiv reading page with AI summaries, built on [dw-dengwei/daily-arXiv-ai-enhanced](https://github.com/dw-dengwei/daily-arXiv-ai-enhanced) (Apache-2.0, see [LICENSE](LICENSE)). Live instance: **https://eryc123y.github.io/daily-arXiv-ai-enhanced/**

Every new paper of the day in your arXiv categories (this instance: cs.CV, cs.AI, cs.LG, cs.CL, stat.ML and cs.GR) (new submissions and same-period cross-lists, not replacements), each with a five-part English summary (TL;DR, motivation, method, result, conclusion). Papers matching research-interest keywords or authors are marked and listed first. The default keywords are grouped into topics (this instance: 2D-to-3D and stereo; weak supervision and data reuse) in [`js/interest-presets.js`](js/interest-presets.js); the page filters by topic first, with arXiv categories as a secondary filter, and keywords can be changed per browser under "Keywords & authors".

## Deploy your own

Everything runs on GitHub's free tier; the page reads its data from whichever repository serves it, so a fork needs no code changes.

1. Fork this repository (the main branch is enough; the first crawl creates the `data` branch), then clone your fork.
2. With [uv](https://docs.astral.sh/uv/) and the [GitHub CLI](https://cli.github.com/) logged in to your account:

   ```bash
   uv sync
   ```

   ```bash
   uv run python -m summaries setup --categories "cs.CV, cs.LG" --run
   ```

   This sets the repository variables, enables the workflows and GitHub Pages, starts the first crawl and prints your page's address. If GitHub has not enabled workflows on the fork yet, it tells you which button to click on the Actions tab; run it again afterwards. Add `--commit-name` and `--commit-email` (your GitHub noreply address) to make data commits under your name instead of the github-actions bot.
3. Choose who writes the summaries:
   - a local coding agent on your machine (default): `uv run python -m summaries run-local --client claude` (or `codex`, `antigravity`), on a cron or launchd schedule; or a Claude Code scheduled task with the prompt in [docs/claude-code-task.md](docs/claude-code-task.md);
   - an LLM API inside GitHub Actions: add your provider's key with `gh secret set` and set `SUMMARY_MODE` to `api` (see API providers below).
4. Put your own interests in [`js/interest-presets.js`](js/interest-presets.js) (named topics with keywords), or edit them per browser under "Keywords & authors" on the page.

## How a day flows

1. **GitHub Actions** ([`run.yml`](.github/workflows/run.yml), 01:30 UTC plus a 07:30 UTC catch-up) reads each category's `/new` listing, drops papers already published in the past week, and commits `data/<date>.jsonl` to the `data` branch. Days without an arXiv announcement (weekends, holidays, late batches) publish nothing and the page keeps the last day.
2. **Summaries** are written to `data/<date>_AI_enhanced_English.jsonl` by one of two modes (below). Until a paper has its summary, the page shows its abstract, says the summary is not written yet, and a progress bar shows how many are ready.
3. **GitHub Pages** serves this branch's static site, which reads both files from the `data` branch.

## Summary modes

Set by the repository variable `SUMMARY_MODE`.

| Mode | Who summarises | Needs |
|---|---|---|
| `claude-code` (default, also when unset) | A local coding agent: a scheduled Claude Code task (Haiku subagents), or `run-local` with Codex, Antigravity or another CLI | That client's subscription; the machine awake |
| `api` | The Actions job, through the provider chosen by `SUMMARY_PROVIDER` (below) | That provider's key secret |

### API providers

| `SUMMARY_PROVIDER` | Key secret | `SUMMARY_MODEL` | Notes |
|---|---|---|---|
| `anthropic` (default) | `ANTHROPIC_API_KEY` | optional, default `claude-haiku-5-5` | Anthropic SDK, low effort, structured output |
| `openai` | `OPENAI_API_KEY` | required | Chat Completions with a strict JSON schema. Set `OPENAI_BASE_URL` to use any OpenAI-compatible server (DeepSeek, OpenRouter, vLLM, Ollama, ...) |
| `gemini` | `GEMINI_API_KEY` | required | Gemini's OpenAI-compatible endpoint |

Optional variables for `openai`/`gemini`: `SUMMARY_REASONING_EFFORT` (for example `low`, only for models that accept it) and `SUMMARY_RESPONSE_FORMAT=json_object` for servers without JSON-schema support. All providers share one retry policy: 429, 5xx and network errors are retried with backoff; another 4xx or a refusal leaves that paper pending; a wrong key or model name stops the run.

Switch to API mode, for example with Gemini:

```bash
gh secret set GEMINI_API_KEY -R Eryc123Y/daily-arXiv-ai-enhanced
```

```bash
gh variable set SUMMARY_PROVIDER --body gemini -R Eryc123Y/daily-arXiv-ai-enhanced
```

```bash
gh variable set SUMMARY_MODEL --body <gemini-model-id> -R Eryc123Y/daily-arXiv-ai-enhanced
```

```bash
gh variable set SUMMARY_MODE --body api -R Eryc123Y/daily-arXiv-ai-enhanced
```

Switch back with `gh variable set SUMMARY_MODE --body claude-code -R Eryc123Y/daily-arXiv-ai-enhanced`. If `api` is set but the provider is not ready (no key secret, no model), the job warns and falls back to `claude-code`. In API mode the local task finds nothing pending and only fills papers the API skipped; it can also be paused in the Claude app.

### The local task (claude-code mode)

Scheduled task `daily-arxiv-summaries`, daily at 10:30, 16:30 and 21:30 local time (MYT), so it starts about an hour after the morning crawl and has two later chances to resume. Each run:

1. checks plan usage before starting and before every wave of subagents (so the job never crowds out your other work on the same subscription; see the fallback below);
2. `uv run python -m summaries status` to find recent days with pending papers;
3. `uv run python -m summaries prepare --date D` writes chunks of 20 pending papers to `.cache/summaries/D/`;
4. Haiku subagents, three at a time, each turn one chunk into a plain-text block file;
5. `uv run python -m summaries merge --date D` validates the blocks, merges them into the day's summary file and pushes it to the `data` branch, after every few chunks;
6. `uv run python -m summaries finish` releases the run's lock.

Progress is committed as it goes and finished papers are skipped, so a run that stops (usage gate, app closed) continues where it left off on the next run. Details: [docs/claude-code-mode.md](docs/claude-code-mode.md).

### Other coding agents (Codex, Antigravity, ...)

The same local job runs through any coding-agent CLI's headless mode; each chunk of 20 papers goes to one call that reads the chunk and writes its summaries file:

```bash
uv run python -m summaries run-local --client codex
```

| `--client` | Command it runs per chunk |
|---|---|
| `claude` | `claude -p <prompt> --model haiku --allowedTools Read,Write` |
| `codex` | `codex exec --sandbox workspace-write <prompt>` |
| `antigravity` | `agy -p <prompt>` (files inside the workspace are allowed by default) |
| `custom` | your own argv, e.g. `--command '["mycli","-p","{prompt}","--model","{model}"]'` |

Useful flags: `--model`, `--parallel 2` (calls at once), `--max-chunks N` (a per-run budget, since only Claude exposes plan usage), `--days 4`. Progress is merged and pushed every few chunks and the day is logged as `local-<client>`, so a run that stops resumes on the next one. Schedule it with cron or launchd, for example `30 10,16,21 * * * cd ~/daily-arXiv-ai-enhanced && uv run python -m summaries run-local --client codex --max-chunks 40 >> .cache/run-local.log 2>&1`. Agents working in this repository get the same instructions from [`AGENTS.md`](AGENTS.md) (Codex, Antigravity) and [`CLAUDE.md`](CLAUDE.md).

### Fallback at the usage gate

When the 5-hour window or the weekly limit reaches **80%**, the task stops using the subscription and runs `uv run python -m summaries handover --date D`:

- it merges and publishes what the subagents finished;
- if the configured API provider is ready (its key secret exists, checked by name with `gh secret list`, and `SUMMARY_MODEL` is set where required), it dispatches [`summarize-api.yml`](.github/workflows/summarize-api.yml) for that date. That Actions job summarises the remaining papers through the same `api` code path, so the day still ends complete;
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

Code map: `daily_arxiv/` (Scrapy spider for the listings), `summaries/` (data-branch publishing, both summary modes, CLI; API providers in `providers.py`, `anthropic_api.py`, `openai_compat.py` around one retry loop in `llm.py`), `index.html`, `css/site.css` and `js/{app,render,data-source,paper-data,interest-presets}.js` (the reading page; bump the `?v=` asset versions in `index.html` on each release so GitHub Pages' cache does not serve stale files; `statistic.html` is upstream's keyword-trends page). `ai/enhance.py` is upstream's OpenAI-compatible summariser, kept but not used by the workflow.

## Changes from upstream

- Metadata comes from the listing page itself, not one arXiv API call per paper; cross-lists are included.
- Deduplication against the past week of the `data` branch, so weekend reruns do not republish Friday.
- The workflow no longer commits to `main`, and has the `contents: write` permission it needs.
- `assets/file-list.txt` lists every day, which fixes the date-range view (upstream #136).
- Summaries are produced by Claude (two modes above); papers without one are shown as pending instead of being dropped.
- Keyword matching uses whole words over title, abstract and TL;DR.
- A three-pane reading layout (topics and filters, paper list, reading pane with the full summary), light and dark, phone width; `j`/`k` move through the list and `/` searches; keyword and author settings are a dialog on the same page. Data access is isolated in `js/data-source.js` so a server or database can replace the static files later.
