# Daily arXiv

> [!CAUTION]
> 若您所在法域对学术数据有审查要求，谨慎运行本代码；任何二次分发版本必须履行合规审查（包括但不限于原始论文合规性、AI合规性）义务，否则一切法律后果由下游自行承担。
>
> If your jurisdiction has censorship requirements for academic data, run this code with caution; any secondary distribution version must remove the entrance accessible to China and fulfill the content review obligations, otherwise all legal consequences will be borne by the downstream.

A daily arXiv reading page with AI summaries, built on [dw-dengwei/daily-arXiv-ai-enhanced](https://github.com/dw-dengwei/daily-arXiv-ai-enhanced) and released under the same licence as upstream: the Modified Apache License in [LICENSE](LICENSE), which is Apache 2.0 with an added disclaimer for third-party content such as arXiv (section 9). This fork changes many upstream files; the git history records each change. Live instance: **https://eryc123y.github.io/daily-arXiv-ai-enhanced/**

Every new paper of the day in your arXiv categories (this instance: cs.CV, cs.AI, cs.LG, cs.CL, stat.ML and cs.GR) (new submissions and same-period cross-lists, not replacements), each with a five-part English summary (TL;DR, motivation, method, result, conclusion). Papers matching research-interest keywords or authors are marked and listed first. The default keywords are grouped into topics (this instance: 2D-to-3D and stereo; weak supervision and data reuse; continual learning; data and representation) in [`js/interest-presets.js`](js/interest-presets.js); the page filters by topic first, then refines by "Has code" and arXiv category, with every count showing what that choice would leave, and keywords can be changed per browser in Settings. Settings also choose a light theme (Preprint, Graphite) and a dark theme (Lilac, Lamplight, Anaglyph), whether the page follows the system or stays light or dark, and whether papers open on alphaXiv or arXiv; all of it is saved in the browser. Papers whose abstract or comments link a code repository (GitHub, GitLab, Codeberg, anonymous review repos) are marked Code, and the Has code refinement shows only those; links that appear only in the PDF are not seen. A linked project page is marked separately.

## Deploy your own

The crawl and the summaries run on your own machine (no GitHub Actions schedule); GitHub stores the `data` branch and serves the page for free. The page reads its data from whichever repository serves it, so a fork needs no code changes.

1. Fork this repository (the main branch is enough; the first crawl creates the `data` branch), then clone your fork.
2. With [uv](https://docs.astral.sh/uv/) and the [GitHub CLI](https://cli.github.com/) logged in to your account:

   ```bash
   uv sync
   ```

   ```bash
   uv run python -m summaries setup --categories "cs.CV, cs.LG"
   ```

   This sets the repository variables (the crawl reads `CATEGORIES`), enables GitHub Pages and prints your page's address. GitHub Pages builds need Actions to be allowed on the repository; if GitHub has disabled it on the fork, setup tells you which button to click (no workflow runs on a schedule). Add `--commit-name` and `--commit-email` (your GitHub noreply address) to make data commits under your name.
3. Crawl and summarise on a schedule, Monday to Friday after arXiv's announcement (00:00 UTC in summer, 01:00 UTC in winter):
   - `uv run python -m summaries ensure-day` crawls today's papers on your machine and backfills days it missed;
   - `uv run python -m summaries run-local --client claude` (or `codex`, `antigravity`) writes the summaries, and `uv run python -m summaries hf-signals --days 7` the Hugging Face upvotes;
   - run them from cron or launchd, or as a Claude Code scheduled task with the prompt in [docs/claude-code-task.md](docs/claude-code-task.md).
4. Put your own interests in [`js/interest-presets.js`](js/interest-presets.js) (named topics with keywords), or edit them per browser in the page's Settings.

### What it costs

Measured on this instance (details in [docs/daily-pipeline.md](docs/daily-pipeline.md#measurements)); API-equivalent list prices, though the local task runs on a Claude plan:

| Step | Per day |
|---|---|
| Crawl and Hugging Face upvotes (on the Mac) | free |
| Summaries, Haiku, 40 papers a call | about $0.27 for 450 papers, $0.53 for 910 |
| Chinese report, one Sonnet call | about $0.16-0.21 |
| The scheduled task around them | 7-9 tool calls; a few percent of a 5-hour window |

On 2026-11-03 a 1,335-paper day took the 5-hour window from 5% to 9% and left the weekly window unchanged. Summaries are written from titles and abstracts only; reading the PDFs would cost 40-50 times as much.

## How a day flows

1. **The crawl** (`summaries ensure-day`, run by the local task) reads each category's `/new` listing on the Mac, drops papers already published in the past week, and commits `data/<date>.jsonl` to the `data` branch. Days without an arXiv announcement (weekends, holidays, late batches) publish nothing and the page keeps the last day. Weekdays the Mac missed (asleep, off, travelling) are backfilled on the next run from the `/recent` listing, which shows the last five announcements, with abstracts from the arXiv API; anything older is reported as a gap. GitHub Actions ran this crawl until 2026-11-08, when GitHub disabled workflows on this fork.
2. **Summaries** are written to `data/<date>_AI_enhanced_English.jsonl` by one of two modes (below). Until a paper has its summary, the page shows its abstract, says the summary is not written yet, and a progress bar shows how many are ready.
3. **GitHub Pages** serves this branch's static site, which reads both files from the `data` branch.

## Summary modes

| Mode | Who summarises | Needs |
|---|---|---|
| Local coding agent (default) | A scheduled Claude Code task (headless Haiku through `run-local`), or `run-local` with Codex, Antigravity or another CLI | That client's subscription; the machine awake |
| API | `uv run python -m summaries api --days 3` on the same machine, through the provider chosen by `SUMMARY_PROVIDER` (below) | That provider's key in the job's environment |

### API providers

The settings are environment variables of the job that runs `summaries api` (or `handover`).

| `SUMMARY_PROVIDER` | Key variable | `SUMMARY_MODEL` | Notes |
|---|---|---|---|
| `anthropic` (default) | `ANTHROPIC_API_KEY` | optional, default `claude-haiku-5-5` | Anthropic SDK, low effort, structured output |
| `openai` | `OPENAI_API_KEY` | required | Chat Completions with a strict JSON schema. Set `OPENAI_BASE_URL` to use any OpenAI-compatible server (DeepSeek, OpenRouter, vLLM, Ollama, ...) |
| `gemini` | `GEMINI_API_KEY` | required | Gemini's OpenAI-compatible endpoint |

Optional variables for `openai`/`gemini`: `SUMMARY_REASONING_EFFORT` (for example `low`, only for models that accept it) and `SUMMARY_RESPONSE_FORMAT=json_object` for servers without JSON-schema support. All providers share one retry policy: 429, 5xx and network errors are retried with backoff; another 4xx or a refusal leaves that paper pending; a wrong key or model name stops the run.

For example with Gemini, in the job's environment: `SUMMARY_PROVIDER=gemini`, `SUMMARY_MODEL=<gemini-model-id>` and `GEMINI_API_KEY`. The local task can run alongside: it finds nothing pending and only fills papers the API skipped.

### The local task

Scheduled task `daily-arxiv-summaries`, at 10:20, 12:20, 16:20 and 21:20 local time (MYT) Sunday to Friday, with the prompt in [docs/claude-code-task.md](docs/claude-code-task.md). A weekday run:

1. `uv run python -m summaries ensure-day` crawls the day's papers when they are still missing and backfills missed weekdays (see How a day flows), then `uv run python -m summaries hf-signals --days 7` refreshes the Hugging Face upvotes;
2. checks plan usage (so the job never crowds out your other work on the same subscription; see the fallback below);
3. `uv run python -m summaries run-local --client claude` summarises 40 pending papers per headless Haiku call (`--tools Read,Write --strict-mcp-config`, so each call starts at about 11,500 tokens instead of 70,000), merging and pushing as it goes;
4. `uv run python -m summaries digest --dir <folder>` writes the day's short Chinese report (one Sonnet call over the site data; code renders it with links that open each paper on the page) and prints a push message.

The evening run resumes anything the morning could not finish. Everything runs only while the Mac is awake and the Claude app is open; days missed for longer than a week cannot be crawled from the listings and are reported as a gap in the task's message. On Sunday `digest-week` puts the week's radar and topic counts on one page. Progress is committed as it goes and finished papers are skipped, so a run that stops (usage gate, app closed) continues where it left off. Details: [docs/claude-code-mode.md](docs/claude-code-mode.md); the design and its measurements (cost per run, PDFs versus abstracts, how accurate abstract-only picks are): [docs/daily-pipeline.md](docs/daily-pipeline.md).

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
- if an API provider is ready in the task's environment (its key variable is set, and `SUMMARY_MODEL` where required), it summarises the remaining papers through the same `api` code path on the Mac, so the day still ends complete;
- otherwise it pauses: the rest of the day stays "summary pending" on the page and the next scheduled run resumes on the subscription. This instance has no key on the Mac, so it pauses.

Every outcome is appended to `logs/summary-runs.jsonl` on the `data` branch (`date`, `path` = `claude-code` / `api` / `api-fallback` / `paused-no-key`, `total`, `done`, `pending`, time, reason). Keys are never printed or stored by the code.

## Data branch

- `data/<date>.jsonl`: one paper per line (`id`, `title`, `authors`, `categories` with the primary first, `summary` = abstract, `comment`, `abs`, `pdf`, optional `code_url`).
- `data/<date>_AI_enhanced_English.jsonl` (`LANGUAGE` variable; older days also have upstream's `_Chinese` files): the same records plus `AI` = `{tldr, motivation, method, result, conclusion}`, only for papers whose summary is complete.
- `data/<date>_hf.json`: upvotes on Hugging Face Daily Papers for that day's papers that were listed there (`{arXiv id: upvotes}`), refreshed by each run of the local task (`uv run python -m summaries hf-signals --days 7`); the page shows them as ▲ badges.
- `assets/file-list.txt`: every jsonl file on the branch, rebuilt on each commit.
- `logs/summary-runs.jsonl`: when each day was crawled (`path` = `crawl`), which summary path ran, and when the daily report was written (`path` = `report`). The page turns it into a status line under the day: crawled, summaries done and by whom (or why they paused), report written.

Raw URL pattern: `https://raw.githubusercontent.com/Eryc123Y/daily-arXiv-ai-enhanced/data/data/<date>.jsonl`.

## Development

```bash
uv sync && uv run pytest -q
```

```bash
node --test tests/js/*.test.js
```

No CI runs while Actions is disabled on this repository, so run both before merging to `main`. The suite never touches the network or the real remote (see `conftest.py`).

Code map: `daily_arxiv/` (Scrapy spider for the listings), `summaries/` (data-branch publishing, both summary modes, CLI; API providers in `providers.py`, `anthropic_api.py`, `openai_compat.py` around one retry loop in `llm.py`; the daily report in `digest.py`, with the page's topic matching in `interests.py`), `index.html`, `css/site.css` and `js/{app,render,data-source,paper-data,interest-presets}.js` (the reading page; bump the `?v=` asset versions in `index.html` on each release so GitHub Pages' cache does not serve stale files; `statistic.html` is upstream's keyword-trends page).

## Changes from upstream

- Metadata comes from the listing page itself, not one arXiv API call per paper; cross-lists are included.
- Deduplication against the past week of the `data` branch, so weekend reruns do not republish Friday.
- The crawl runs on the maintainer's machine instead of a GitHub Actions schedule, and backfills days it missed; nothing commits to `main`.
- `assets/file-list.txt` lists every day, which fixes the date-range view (upstream #136).
- Summaries are produced by Claude (two modes above); papers without one are shown as pending instead of being dropped.
- Keyword matching uses whole words over title, abstract and TL;DR.
- A three-pane reading layout (topics and filters, paper list, reading pane with the full summary), light and dark, phone width; `j`/`k` move through the list and `/` searches; keyword and author settings are a dialog on the same page. Data access is isolated in `js/data-source.js` so a server or database can replace the static files later.
