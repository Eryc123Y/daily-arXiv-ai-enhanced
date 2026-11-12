# Daily pipeline: design and measurements

Written 2026-11-02, when two jobs produced the same daily digest: an older claude.ai routine ("Arxiv daily digest", Opus, every day at 16:30) that crawled arXiv in a browser and read PDFs, and the Claude Code scheduled task `daily-arxiv-summaries`, which wrote the site summaries and then skipped its own digest because the routine had already written one. Weekly plan usage reached 96% that afternoon.

## Decision

| Step | Done by | Why |
|---|---|---|
| Crawl the `/new` listings, dedupe against the past week, publish `data/<date>.jsonl` | Code (`summaries ensure-day` on the Mac; GitHub Actions `run.yml` until 2026-11-08) | It takes 25 seconds and no tokens. The routine needed double fetches and SHA-256 checks to trust a browser crawl, and its runbook lists the failure modes: cached WebFetch pages, proxy 403s, HTTP 429 after a 45-second script. |
| Crawl on the Mac, not in GitHub Actions | Code (`summaries ensure-day`) | GitHub skipped scheduled runs (01:30 UTC on 2026-11-02) and then disabled workflows on this fork (from 2026-11-08, HTTP 422 on dispatch); Eric decided on 11-09 to run everything from the local task. |
| Backfill days the Mac missed | Code (`ensure-day`: `/recent` listing plus the arXiv API for abstracts) | `/new` shows only the latest announcement. `/recent` shows the last five; a live check on 11-09 matched the published 11-05 (512 of 512) and 11-06 (492 of 492) exactly. Older days are reported as a gap. |
| Hugging Face upvotes | Code (`summaries hf-signals --days 7`, each task run) | Was `signals.yml` every four hours in Actions. |
| Topic tagging and radar candidates | Code (`summaries/interests.py`, the brief's regex) | The page already tags topics with these keywords. Keywords alone found 6 of 8 past radar picks and 6 of 7 stereo picks, so they make the shortlist, not the decision. |
| Five-part English summaries | Haiku, abstract only, headless (`run-local --client claude`) | See the cost and PDF measurements below. |
| Picks, radar grades and the report text | One Sonnet call over the day's candidates and every title and TL;DR; code renders the report | Sonnet on abstracts recovered every past radar and stereo pick (15 of 15); Haiku on abstracts recovered 2 of 7 stereo picks. |
| Full text | Only for at most two radar papers a day that the first call marks for a check | Abstracts never produced a "medium" grade that full text gave (0 of 3). |

There is one digest pipeline: the scheduled task. The claude.ai routine is paused, not deleted (`RemoteTrigger` id `trig_0114EXEPpDqkb6dQDp7AoV3C`).

## Daily schedule

Times are Malaysia time (UTC+8). arXiv announces at 20:00 US Eastern, which is 09:00 MYT in winter and 08:00 MYT in summer, Monday to Friday mornings.

| When | What |
|---|---|
| 10:20 (Mon-Fri) | Scheduled task: `ensure-day` (crawls the day if it is missing, backfills missed days), `hf-signals`, usage gate, `run-local` summaries, `digest`, one push notification. The report is the task's final message and `digests/<date>.md` in the vault. |
| 12:20, 16:20 (Mon-Fri) | Same task as the morning, for days when arXiv announces late. The listing was still the previous day's at 10:34 on 2026-11-05 (it appeared before 13:03) and at 12:15 on 11-04; on 11-03 it appeared between 16:30 and 19:00. On a normal day the report already exists and the run stops after a few calls. |
| 21:20 (Mon-Fri) | Same task again with `digest --final`: resumes summaries stopped by the usage gate, writes the report if the morning had no batch yet, and on a day without any batch writes a two-line note. Otherwise it stops after a few calls. |
| 10:20 (Sun) | `missed` (look-back radar papers from earlier Sundays that were in one of our batches go to `missed.md` in the vault), then `digest-week` (the week's radar rows and topic counts, no model call), then one Sonnet subagent looks for up to three older papers for the radar (two alphaXiv searches). The 21:20 Sunday run stops at once. |

Cron for the task: `20 10,12,16,21 * * 0-5`.

The phone gets the report from the claude.ai routine "Arxiv daily digest", which posts `digests/<date>.md` into its chat at 11:30. The task's own push rarely arrives: `PushNotification` goes out through Remote Control, a scheduled run is an unattended session, and an unattended session cannot turn Remote Control on, so the tool answers "Mobile push not sent (Remote Control inactive)" (seen on 2026-10-29 and 2026-11-03; interactive sessions do deliver). The task says so in its last line.

Journal and conference papers (spec [S1](specs/s1-sources-beyond-arxiv.md)) come from a feed command, not from a model: when `FEED_COMMAND` is set, `ensure-day` runs it after the arXiv crawl, every day of the week, asking for the journal and conference papers of the watch list (`--kinds journal,conference`; LitScout's default is journals only) since the cursor on the `data` branch (`assets/feed-cursor.json`, one cursor for both kinds), and publishes the new ones in the same raw file as today's arXiv papers, so the summary job, `status` and the page see one list per day. They go under the day they were fetched, not their publication date: a journal paper is often listed weeks after it is dated, and filed under that date it would land on a day nobody reopens. The cursor moves in the commit that publishes the papers, so a run after days off publishes them once and a second run nothing; the feed's abstracts stay in the local work folder because the `data` branch is public, and a paper without one is listed with title, venue and link but never counted as pending. Abstracts often come late (Crossref lists a fresh IEEE paper the day it is registered; OpenAlex adds the abstract a day or so later; on 2026-11-11, 41 of 220 venue papers had none), so each run asks again for the last four days even when the cursor is newer: a paper published in that window without an abstract that now has one stays on its own day, gets `has_abstract: true`, keeps the abstract locally and becomes pending there (`abstracts_added` in the feed report); it is not counted against the burst cap and does not reappear in today's report. That window is keyed on the day the source listed the paper, so a paper whose abstract comes later than that never gains one through the feed (on 2026-11-12, 41 of 2026-11-11's feed papers still had none). `ABSTRACTS_COMMAND` closes the gap: a JSON argv list like `FEED_COMMAND` (LitScout's `abstracts`, which looks papers up in OpenAlex, Semantic Scholar, arXiv, Crossref, Europe PMC and keyed publisher APIs). After the feed step, `ensure-day` collects the feed records of the last 60 days' raw files that have `has_abstract: false` and no abstract in the local work folder, newest day first, at most 200, and writes one JSON line per record to the command's stdin: `{"id", "doi"?, "arxiv"?, "title"?}` (`arxiv` is the id when it has no `doi:`, `openreview:` or `url:` prefix). The command prints one line per input, in order, `{"id", "abstract": string|null, "source": string|null}`, and exits 0. Abstracts found are saved locally and their records flagged `has_abstract: true` on the days they were first published, in one commit, as the re-request window does; the papers are then pending for `run-local` with nothing else changed. Any other answer (non-zero exit, a malformed line, an id out of order, a wrong number of lines) saves and flags nothing. ensure-day's JSON reports it as `abstracts`: `{"status": "off"}` when the variable is unset, else `status` ("ok", or "error" with `reason`), `asked`, `filled`, `by_source` (filled papers by the source the command named), `still_lacking` (records in the window still without an abstract, beyond the 200 asked included) and `commit`. Without `FEED_COMMAND` the step reports `feed: "skipped"` and arXiv runs as before. A venue marked `match: "topics"` in the watch list (CVPR, NeurIPS, ACM MM, ACL, EMNLP, AAMAS, IEEE TIT and the other large venues) contributes only papers whose title or abstract matches an interest keyword, with the matching the daily report and the page use; the others are dropped before dedupe, the burst cap and the summaries, and `ensure-day` counts them per venue in the feed report's `off_topic`. Every crawl and feed commit also carries `assets/venues.json`, the watch list's names, kinds, areas and top flags (`[{name, kind, area, top}]`, nothing else), which the page groups venue papers by; when neither ran, `ensure-day` publishes it on its own if it changed and reports `venues: "published"`. Every commit that writes a raw file also carries `assets/venue-days.json`, how many journal and conference papers each day's raw file holds (`{"2026-11-11": 187}`, days with none left out, nothing else), which the page's weekly stream lists its weeks from. A commit recounts the days it writes on top of the published counts (all days when there are none); `ensure-day` recounts every raw file once per run (about 15 seconds) and publishes the file in the same `venues: "published"` commit when it was missing or stale. A fork without it still works: the page then counts venue papers from the day files.

`ingest` logs a `crawl` entry (when the papers landed) in `logs/summary-runs.jsonl`, beside the summary and report entries. Sunday's page ends with a health table built from that log (data landed, summaries finished, report written, pauses), the on-time count (weekdays with the report by 11:30, among days whose papers landed by 10:00) and the misses of the last thirty days from `missed.md`, and the site's status line says when the latest crawl found that arXiv has not announced the day yet.

## Report format

About one screen in Chinese: the day's count and a link to the day on the page; one radar line per possible collision (level, whether the full text was read, the reason); up to three picks per interest topic with title, a one-line gist and a link that opens that paper (`#day=<date>&topic=<topic>&paper=<id>`; the page now opens a linked paper on phones and falls back to All papers when the topic would hide it); up to two other papers; an optional one-line note. When the previous batch has papers with at least 10 upvotes on Hugging Face Daily Papers (`data/<day>_hf.json`, refreshed every four hours by `signals.yml` with no model), a line names the top two: the morning report is too early for today's upvotes, so it reports what the community picked from the last batch. A radar paper is not repeated under its topic. A pick whose listing links code ends with ` · [代码](url)` (` · [项目页](url)` for a project page), from the `code_url` the spider keeps, and the writer sees `[code]` beside such candidates so it can prefer them between papers of similar value. Rendered by `summaries/digest.py`; the model only writes plain picks lines, so links and layout cannot drift.

Journal papers (spec S1, R9) are candidates on the same footing: they match topics on their title and the abstract in the local work folder (their TL;DR when it is not there), the writer sees `[venue]` beside them, and they may go under a topic, the radar or other. In the report a journal paper's line carries its venue (`（IEEE TCSVT）— gist`, `（IEEE TPAMI；中，仅摘要）` on the radar) and its link opens it on the page with the id URL-encoded (`paper=doi%3A10.1109%2F...`); there is no arXiv link. The count line reads `555 篇新论文 · 期刊 150 篇` and the push `555 篇 + 期刊 150 篇`. On a day with journal candidates a short section `来自期刊`, after every other list, gives their count by venue, how many journal papers the report already lists above (`其中 3 篇已列在上面`), and up to two more journal papers the writer chose (`journal | id | gist`, any of the day's journal papers, keyword matches first); it says `今日无精选` only when no journal paper appears anywhere in the report. An arXiv-only day reads exactly as before, apart from the title: the report is `LitScout 日报` and Sunday's page `LitScout 本周回顾` (the site's name since PR 38); `arXiv` stays where it names the source (`arXiv 2026-11-11 批次`, the push's `arXiv 11-11：…`). No command parses past reports by their title. The full-text check reads arXiv PDFs only: a journal paper is checked only when its id is an arXiv ID. Sunday's page counts journal picks under their topics and adds one line with the week's journal papers by venue. `digest --dry-run --dir <scratch>` writes the report into a scratch folder and leaves the data branch's run log alone (work files go to `<scratch>/work`).

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

When the report's `claude -p` call fails (on 2026-11-05 and 11-06 its sign-in had expired: "OAuth session expired and could not be refreshed", and both days had no report until it was rerun by hand), `digest` asks Codex instead (`codex exec -s read-only`, `--fallback` to change or `''` to turn off; never with an explicit `--command`). The full-text check then goes to the client that answered. The output's `client` names the writer, `problems` carries the claude error, and the task adds a line asking Eric to sign in again. The summaries already had a fallback: Haiku subagents when every headless chunk fails.

At 80% of the 5-hour or weekly window the task stops using the subscription and runs `summaries handover`, which summarises the rest of the day through the API on the Mac when a provider key is in the task's environment and otherwise pauses until a later run (`paused-no-key` in `logs/summary-runs.jsonl`, as on 2026-11-02). With Haiku 5.5 an API fallback costs about $0.15 for a 450-paper day. Until 2026-11-08 this dispatched `summarize-api.yml` in Actions with the key as a repository secret; that workflow is deleted, and the Mac has no key, so the fallback pauses.

`SUMMARY_PROVIDER` defaults to `anthropic` and `SUMMARY_MODEL` to `claude-haiku-5-5`.

## Open items

- The scheduled task's model cannot be set through the scheduled-tasks tool, so it runs on the app's default model (Opus 5.5 on 2026-11-02, Sonnet on 2026-10-30). It now makes few calls; choosing Sonnet for the task in the app would halve its cost again.
- Everything runs only while the Mac is awake and the Claude app is open. A trip longer than a week leaves days that `/recent` no longer lists; `ensure-day` names them in `gap`, and they would need a crawl of the arXiv API by submission date, which does not match announcement days exactly.
- The page has been served from Cloudflare at https://litscout.turing2234.com/ since 2026-11-12 (Worker `litscout-daily`, deployed by Workers Builds on each push to `main`), because GitHub Pages builds run on Actions and GitHub disabled Actions on this fork on 2026-11-09. Data updates need no deploy (the page reads the `data` branch directly). The old GitHub Pages address redirects to the new one, but only once Pages has built a `main` that has the redirect, which needs Actions allowed on the repository at least once.
- The radar regex lives in `DIGEST/project-brief.md` (lines `SUP =`, `REUSE =`, `INFO =`, `GROUND =`), which Eric's project session maintains; the digest reads it on every run.
