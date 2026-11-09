# Daily pipeline: design and measurements

Written 2026-11-02, when two jobs produced the same daily digest: an older claude.ai routine ("Arxiv daily digest", Opus, every day at 16:30) that crawled arXiv in a browser and read PDFs, and the Claude Code scheduled task `daily-arxiv-summaries`, which wrote the site summaries and then skipped its own digest because the routine had already written one. Weekly plan usage reached 96% that afternoon.

## Decision

| Step | Done by | Why |
|---|---|---|
| Crawl the `/new` listings, dedupe against the past week, publish `data/<date>.jsonl` | Code (GitHub Actions, `run.yml`) | It takes 25 seconds and no tokens. The routine needed double fetches and SHA-256 checks to trust a browser crawl, and its runbook lists the failure modes: cached WebFetch pages, proxy 403s, HTTP 429 after a 45-second script. |
| Start the crawl when GitHub's schedule skipped it | Code (`summaries ensure-day`, from the Mac) | The 01:30 UTC run of 2026-11-02 never fired. |
| Crawl on the Mac when Actions refuses the dispatch | Code (`summaries ensure-day` runs the spider and `ingest`'s publishing locally, today's listing only) | GitHub disabled workflows on this fork on 2026-11-08; no day was crawled until the 11-09 fallback. |
| Topic tagging and radar candidates | Code (`summaries/interests.py`, the brief's regex) | The page already tags topics with these keywords. Keywords alone found 6 of 8 past radar picks and 6 of 7 stereo picks, so they make the shortlist, not the decision. |
| Five-part English summaries | Haiku, abstract only, headless (`run-local --client claude`) | See the cost and PDF measurements below. |
| Picks, radar grades and the report text | One Sonnet call over the day's candidates and every title and TL;DR; code renders the report | Sonnet on abstracts recovered every past radar and stereo pick (15 of 15); Haiku on abstracts recovered 2 of 7 stereo picks. |
| Full text | Only for at most two radar papers a day that the first call marks for a check | Abstracts never produced a "medium" grade that full text gave (0 of 3). |

There is one digest pipeline: the scheduled task. The claude.ai routine is paused, not deleted (`RemoteTrigger` id `trig_0114EXEPpDqkb6dQDp7AoV3C`).

## Daily schedule

Times are Malaysia time (UTC+8). arXiv announces at 20:00 US Eastern, which is 09:00 MYT in winter and 08:00 MYT in summer, Monday to Friday mornings.

| When | What |
|---|---|
| 09:17, 09:47, 11:23, 15:37 (Mon-Fri) | GitHub Actions crawl (`run.yml`). A run that finds nothing new publishes nothing. |
| 10:20 (Mon-Fri) | Scheduled task: `ensure-day` (starts the crawl and waits if the day is missing), usage gate, `run-local` summaries, `digest`, one push notification. The report is the task's final message and `digests/<date>.md` in the vault. |
| 12:20, 16:20 (Mon-Fri) | Same task as the morning, for days when arXiv announces late. The listing was still the previous day's at 10:34 on 2026-11-05 (it appeared before 13:03) and at 12:15 on 11-04; on 11-03 it appeared between 16:30 and 19:00. On a normal day the report already exists and the run stops after a few calls. |
| 21:20 (Mon-Fri) | Same task again with `digest --final`: resumes summaries stopped by the usage gate, writes the report if the morning had no batch yet, and on a day without any batch writes a two-line note. Otherwise it stops after a few calls. |
| 10:20 (Sun) | `missed` (look-back radar papers from earlier Sundays that were in one of our batches go to `missed.md` in the vault), then `digest-week` (the week's radar rows and topic counts, no model call), then one Sonnet subagent looks for up to three older papers for the radar (two alphaXiv searches). The 21:20 Sunday run stops at once. |

Cron for the task: `20 10,12,16,21 * * 0-5`.

The phone gets the report from the claude.ai routine "Arxiv daily digest", which posts `digests/<date>.md` into its chat at 11:30. The task's own push rarely arrives: `PushNotification` goes out through Remote Control, a scheduled run is an unattended session, and an unattended session cannot turn Remote Control on, so the tool answers "Mobile push not sent (Remote Control inactive)" (seen on 2026-10-29 and 2026-11-03; interactive sessions do deliver). The task says so in its last line.

`ingest` logs a `crawl` entry (when the papers landed) in `logs/summary-runs.jsonl`, beside the summary and report entries. Sunday's page ends with a health table built from that log (data landed, summaries finished, report written, pauses), the on-time count (weekdays with the report by 11:30, among days whose papers landed by 10:00) and the misses of the last thirty days from `missed.md`, and the site's status line says when the latest crawl found that arXiv has not announced the day yet.

## Report format

About one screen in Chinese: the day's count and a link to the day on the page; one radar line per possible collision (level, whether the full text was read, the reason); up to three picks per interest topic with title, a one-line gist and a link that opens that paper (`#day=<date>&topic=<topic>&paper=<id>`; the page now opens a linked paper on phones and falls back to All papers when the topic would hide it); up to two other papers; an optional one-line note. When the previous batch has papers with at least 10 upvotes on Hugging Face Daily Papers (`data/<day>_hf.json`, refreshed every four hours by `signals.yml` with no model), a line names the top two: the morning report is too early for today's upvotes, so it reports what the community picked from the last batch. A radar paper is not repeated under its topic. A pick whose listing links code ends with ` · [代码](url)` (` · [项目页](url)` for a project page), from the `code_url` the spider keeps, and the writer sees `[code]` beside such candidates so it can prefer them between papers of similar value. Rendered by `summaries/digest.py`; the model only writes plain picks lines, so links and layout cannot drift.

## Measurements

Costs are API-equivalent list prices (Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per million input/output tokens; Haiku costs five times as much on prompts over 100K tokens), computed from the `usage` records in the session transcripts or from `claude -p --output-format json`. Plan usage is a different meter, but it scales with the same tokens.

### Where the cost went

| Run | Papers | Orchestrator | Haiku | Total | Plan usage |
|---|---|---|---|---|---|
| 2026-11-02 21:44, subagents | 450 | Opus, 51 calls, 6.5M cache-read tokens: $3.70 | 24 subagents: $0.77 | $4.47 | 5-hour window +2% |
| 2026-10-30, subagents | 910 | Sonnet: $2.88 | 46 subagents: $1.50 | $4.38 | 5-hour 41% to 48%, weekly 67% to 67% |
| Idle run (nothing pending), two measured | 0 | Opus: $0.74 | none | $0.74 | |

- Every general-purpose subagent call starts at 70,037 tokens of system prompt and tool definitions (most of them MCP tools); the 20 abstracts it summarises are about 10,000. A third of the Haiku calls (25 of 75, 45 of 141) crossed 100K tokens and paid five times the price.
- The routine's logs carry no token counts. On 2026-10-30 it took 23 Opus turns, two full PDF reads of about 10,000 tokens each, alphaXiv searches and a browser crawl, every day including weekends.

The new path, measured on real chunks of 2026-11-02:

| Step | Measured |
|---|---|
| `claude -p --model haiku --tools Read,Write --strict-mcp-config` | 11,500 tokens before any work (instead of 70,037) |
| 20-paper chunk / 40-paper chunk | $0.020 / $0.023, every block parsed. 40 papers cost about what 20 do, so chunks are now 40. |
| Summaries per day | about $0.27 for 450 papers, $0.53 for 910 |
| Report writer (Sonnet, one call, no prompt cache) | 94,600 input and 1,600 output tokens, $0.21 for 450 papers; with TL;DRs in the "other papers" list cut to 160 characters the prompt went from 230k to 179k characters (about $0.16) |
| Orchestrator | 7-9 tool calls instead of 51 |

### Haiku reading PDFs instead of abstracts

| Input per paper | Tokens |
|---|---|
| Title and abstract | 522 (3.04 characters per token) |
| Read tool on the PDF, pages 1-20 | about 22,000 (about 1,220 per page) |
| Full text through pdftotext | about 27,000 for the median paper (67,700 characters at 2.47 per token); 16,000 before the references |

Sample: 46 papers from 2026-10-30 and 2026-11-02, median 19 pages, 319 MB of PDFs. Reading PDFs means 40-50 times the input tokens: roughly $2-4 a day at Haiku prices for 450-900 papers instead of $0.27-0.53, plus 3-6 GB of downloads a day, which at arXiv's one request per three seconds takes 25-45 minutes before any model runs. The site summaries are for triage, so abstracts stay.

### Abstract-only classification

46 papers: 24 picks from the routine's digests of 2026-10-30 and 2026-11-02 (8 radar, 7 stereo, 9 other), 12 keyword or regex hits it did not pick and 10 random papers. Each was labelled for the four topics and a radar level three times: Haiku from the abstract, Sonnet from the abstract, Sonnet from the full text (main body before the references).

| | Sonnet, abstract | Haiku, abstract | Sonnet, full text |
|---|---|---|---|
| Past radar picks flagged | 8/8 | 7/8 | 8/8 |
| Past stereo picks in the stereo topic | 7/7 | 2/7 | 7/7 |
| Negatives flagged on the radar | 0/22 | 3/22 | 7/22 |

Sonnet on abstracts against Sonnet on full text: topic agreement 89-98% (Cohen's kappa 0.71-0.85); radar flag agreement 76% (kappa 0.46). The disagreements go one way: full text adds "borrow" flags (10 papers) and raises three papers from "borrow" to "medium" that the abstract left at "borrow" (2610.40564, 2610.37842, 2610.40945; the routine also rated 2610.40564 medium after reading its PDF). Abstracts are enough for topics and for deciding what to look at; a "medium" or "high" grade needs the full text, which is what the brief already asks. Cost of this check: Sonnet full text $3.41 for the 46 papers, Sonnet abstracts $0.19, Haiku abstracts $0.01.

On 2026-11-02, in two reruns, the new report's radar named the same two papers as the routine's (2610.41073 and 2610.40945, both "borrow") plus a third that varied between runs, and its stereo section picked the same three adjacent papers the routine listed (2610.41190, 2610.42092, 2610.41258).

## Usage gate and fallback

At 80% of the 5-hour or weekly window the task stops using the subscription and runs `summaries handover`, which dispatches `summarize-api.yml` when the provider's key secret exists and otherwise pauses until a later run (`paused-no-key` in `logs/summary-runs.jsonl`, as on 2026-11-02). With Haiku 5.5 an API fallback costs about $0.15 for a 450-paper day. To turn it on, set the secret once (the value is typed at the prompt, not on the command line):

```bash
gh secret set ANTHROPIC_API_KEY -R Eryc123Y/daily-arXiv-ai-enhanced
```

`SUMMARY_PROVIDER` defaults to `anthropic` and `SUMMARY_MODEL` to `claude-haiku-5-5`.

## Open items

- The scheduled task's model cannot be set through the scheduled-tasks tool, so it runs on the app's default model (Opus 5.5 on 2026-11-02, Sonnet on 2026-10-30). It now makes few calls; choosing Sonnet for the task in the app would halve its cost again.
- The radar regex lives in `DIGEST/project-brief.md` (lines `SUP =`, `REUSE =`, `INFO =`, `GROUND =`), which Eric's project session maintains; the digest reads it on every run.
