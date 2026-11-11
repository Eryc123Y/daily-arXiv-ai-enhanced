# Spec: sources beyond arXiv, and a new name (S1)

Status: decided, 2026-11-11. Requested by Eric on 2026-11-11; his answers are in "Decisions" below. Nothing here is built yet.

## Problem

The site reads only arXiv. A measurement on 2026-11-04 ([arxiv-coverage.md](../measurements/arxiv-coverage.md)) found that arXiv holds 62-85% of top ML and CV conference papers, but only 8-50% of the journals where stereo and 3D-video work appears (TCSVT 10%, TVCG 30%, TIP 38%, TOG 50%) and none of Journal of Vision. So for the "2D-to-3D and stereo" topic the daily page misses most journal papers, and Eric finds them late or by accident.

## What is known today

| Fact | Evidence |
|---|---|
| The sources behind the paper-search MCP find published papers in Eric's venues | 75 papers from 15 venues searched by title on 2026-11-04: 74 found, including 45 of the 46 that are not on arXiv ([LitScout evaluation](https://github.com/Eryc123Y/litscout-mcp/blob/main/docs/evaluation-paper-search-mcp.md)) |
| That test says nothing about speed | The 75 papers were from 2023-2024. How many days after publication a paper appears in OpenAlex, Crossref or OpenReview is **not measured** |
| ICML, ICLR and JMLR are thin in OpenAlex | The 11-04 sample got no papers for them; they need OpenReview or the proceedings site |
| The MCP is keyword search for an agent, not a feed | Only its OpenAlex tool takes a date filter. A live query on 2026-11-11 returned works dated 11-05 to 11-09, returned the same paper from OpenAlex and OpenReview as two records, and returned a journal version of a paper that already had citations |
| An MCP can only be called by a model | The daily crawl is plain code today and costs no tokens ([daily-pipeline.md](../daily-pipeline.md)) |
| LitScout, Eric's own MCP, is not deployed | v0.1 is on branch `feat/v0.1` (169 tests); its coverage check stopped when the shared OpenAlex quota ran out. `watch` ("new since a date") is in its v0.2 backlog |

So the page does not call the MCP. The pipeline gets a **feed**: code that asks each source for papers new since the last run, the same way it crawls arXiv.

## Goals

1. Papers from a watch list of venues appear on the page within a measured, stated delay of their publication, without a paper appearing twice.
2. The extra reading stays small: after topic matching, at most about 10 extra matched papers a day on average (to be confirmed by Phase 0).
3. Every paper links to a lawful copy when one exists (open-access link), and otherwise to the publisher's DOI page.
4. A fork with no API keys still works as today, with arXiv only.
5. The site's name and wording no longer claim it is only arXiv.

## Non-goals

- **Sci-Hub or any scraping.** Sources are official APIs and open-access indexes only (decided with Eric, 2026-11-11).
- **Publisher full text** (Elsevier, IEEE Xplore). Summaries stay abstract-based; full text is LitScout v0.3, gated on each publisher's terms.
- **Everything OpenAlex lists.** Thousands of computer-science works appear a day, many from venues nobody reads. The feed is a watch list, not a firehose.
- **Search across sources on the site.** That is M3 (search) and LitScout's `search` tool.
- **Moving the pipeline off the Mac.** Noted under Later; it belongs with the M2 backend.

## User stories

- As Eric, I want new TCSVT, TIP, TVCG, TOG and Journal of Vision papers on the same page as arXiv, so that the stereo topic shows me journal work I now miss.
- As Eric, I want a paper that is on arXiv and later in a journal to stay one entry, marked with its venue, so that I do not read it twice.
- As Eric, I want to see where each paper comes from and to filter by source, so that I can read "journals only" on a slow day.
- As Eric returning from a trip, I want the feed to pick up from the last successful run, so that days the Mac was off are not lost (arXiv's `/new` page cannot do this beyond a week; date-based APIs can).
- As a classmate with my own fork and no keys, I want the site to work with arXiv alone and say which sources are off, so that I am not blocked by setup.

## Phases and requirements

### Phase 0: measure first (no decision needed, one session, about a day)

- **R0** A script and a note, `docs/measurements/source-freshness.md`, for a two-week look-back over the 15 venues of the 11-04 sample plus ICLR, ICML and NeurIPS on OpenReview. For OpenAlex, Crossref and OpenReview it reports per venue:
  - papers per day, and how many remain after matching Eric's four topics;
  - delay in days between the publication date and the day the source first listed the paper;
  - share that has an abstract, share that has an open-access link, share already on arXiv;
  - how many OpenAlex "new" works are journal versions of papers the site already published.
  - Acceptance: the note states, for each source, "daily", "weekly" or "not worth it" with the numbers behind it, and how much OpenAlex quota one day of the feed costs.

### Phase 1: the feed and the record (must have)

- **R1 Feed.** One command returns records new since a stored cursor for each source on the watch list, and moves the cursor only after a successful publish. Acceptance: a run after five missed days publishes all five days' papers once; a second run publishes nothing.
- **R2 No duplicates.** A paper is matched to an existing record by arXiv ID, then DOI, then normalised title plus first author. Acceptance: on the Phase 0 sample, no two published records have a title similarity above 0.9.
- **R3 Record.** Every record carries `source`; non-arXiv records also carry `venue`, `doi`, `published` and, when one exists, `oa_url`. arXiv records are unchanged, so old days and forks keep working. Acceptance: the existing tests pass untouched and the page renders a mixed day.
- **R4 Summaries.** Non-arXiv papers get the same five-part summary from their abstract. Papers whose source gives no abstract are listed with title, venue and link, and are not counted as pending. Acceptance: `status` never shows a paper as pending forever.
- **R5 Keys optional.** With no key set, the feed is skipped, the arXiv crawl runs, and `ensure-day` says which sources were skipped. Acceptance: the suite and a keyless run pass.
- **R6 Lawful by construction.** The feed's source list is fixed in code to official APIs; open-access links come only from OpenAlex or Unpaywall. Acceptance: a test fails if a source outside the list is configured.

### Phase 2: the page and the report (must have)

- **R7 Source on the page.** Each paper shows its source or venue; the left pane has a source filter with counts, next to topics and categories. Acceptance: counts follow the same "what this choice would leave" rule as the other filters.
- **R8 Links.** A non-arXiv paper opens its open-access copy when there is one, else its DOI page; the reader says which. Acceptance: no link to a PDF host that is not the publisher, a repository or arXiv.
- **R9 Report.** The daily report's candidates include non-arXiv papers, labelled with their venue. Acceptance: one report on a mixed day reads correctly to Eric.

### Phase 3: the name (must have, after Q6)

- **R10** The page title, logo text, README and report header use the new name; "arXiv" remains only where it names the source. Acceptance: no user-facing string says the site covers only arXiv.

### Should have

- An arXiv record gains `venue` and `doi` when the paper is later published ("published in TCSVT"), instead of a second entry.
- The status line shows one "crawled" part per source, and a source that failed.
- OpenReview decisions and ratings beside ICLR, ICML and NeurIPS papers (from LitScout's `reviews`).

### Later

- The crawl and feed on a Cloudflare cron with the M2 backend, so they no longer need the Mac awake.
- Publisher abstracts stored behind the M2 login; publisher full text with Eric's own entitlements.
- Citation counts and other signals from Semantic Scholar.

## Success measures

| Measure | Target | Read from |
|---|---|---|
| Watch-list papers on the page within the delay Phase 0 states | 90% | A monthly rerun of the Phase 0 script |
| Duplicate entries | 0 in a 100-paper spot check | Same rerun |
| Extra matched papers a day | about 10 or fewer on average | Run log |
| Papers Eric finds elsewhere that the watch list should have shown | 0 a month at venues on the list | `missed.md` |
| Extra summary cost | under 20% above an arXiv-only day | Run log (papers per day) |

## Risks and dependencies

- **Freshness is unknown.** If a source lists papers weeks late, a daily feed has no value for it; Phase 0 decides, and the fallback is a weekly "venue watch" on Sunday's page.
- **OpenAlex quota is shared with LitScout.** LitScout's 600-paper check used it up on 2026-11-11. The feed needs a daily budget and a clear "quota reached" status.
- **Abstract rights.** Publisher abstracts are often copyrighted; the roadmap already keeps them off the public `data` branch (see Q3).
- **Two repositories.** If the feed lives in LitScout, a session is already working in its `feat/v0.1` worktree; feed work there starts only after that branch is merged.
- **Time.** Eric's exam is on 2026-11-16; he is away from 11-26 and the Mac may be off. Feature work stops in January.

## Decisions (Eric, 2026-11-11)

Eric's rule for the details: he must be able to see everything he needs on his own page; how that is done is the builder's call.

| # | Question | Decision |
|---|---|---|
| Q1 | Who builds the feed? | LitScout gets `watch` ("new since a date" for a list of venues) and this pipeline runs it as a local command, as it runs Scrapy. It keeps the 11-04 decision of one set of source adapters, in LitScout. Starts after LitScout's `feat/v0.1` branch is merged. |
| Q2 | What does the feed watch? | High-quality venues only: the watch list below, kept in one file. No keyword queries across all venues. |
| Q3 | Abstracts of non-arXiv papers | The `data` branch is a public GitHub repository, so files there can be downloaded by anyone, not only read on the page. Publisher abstracts are often copyrighted, so they are not published there. Eric still sees what he needs: title, authors, venue, our five-part summary (written from the abstract, which stays in the local work folder) and one click to the abstract on the publisher's page; after M2's login, the abstract itself in the reader. |
| Q4 | Record identity | `id` stays the one key: the arXiv ID as today, else `doi:<doi>`, else `openreview:<forum id>`. Shapes in `summaries/shapes.py` and `js/types.js`. |
| Q5 | Daily or weekly per source | By Phase 0's numbers: a source that lists papers within 3 days (median) of publication goes on the daily page; a slower one goes on Sunday's page as "new in your venues this week", so a two-week-old journal paper is not shown as today's news. |
| Q6 | The name | **LitScout**: the site becomes LitScout's reading page ("LitScout Daily"); both projects share one name and one set of visual assets. The title, logo and README change when the second source ships; the address changes once, with the move to Cloudflare Pages in M2. |

### Watch list v1 (Q2)

Chosen for Eric's topics (stereo and 3D video, weak supervision and data reuse, continual learning, representation) from CCF-A and CORE A* venues, plus the venues the 11-04 measurement showed are mostly missing from arXiv. Edited in one file; Phase 0 measures each.

| Kind | Venues |
|---|---|
| ML and CV conferences | CVPR, ICCV, ECCV, NeurIPS, ICML, ICLR, AAAI, IJCAI, ACM MM |
| Graphics and VR | ACM TOG (SIGGRAPH, SIGGRAPH Asia), IEEE TVCG (IEEE VR, ISMAR), Eurographics (CGF) |
| Journals | IEEE TPAMI, IJCV, IEEE TIP, IEEE TCSVT, JMLR, TMLR |
| Vision science | Journal of Vision |

## How the work is run

Eric decided Q1 to Q6 on 2026-11-11; the main session writes each brief, reviews each pull request and reports. One session per row; rows 2 and 3 can run at the same time once Q3 and Q4 are settled, because they touch different files.

| # | Session | Where | Starts when |
|---|---|---|---|
| 0 | Freshness measurement (R0) | this repository, `docs/measurements/` | now; no decision needed |
| 1 | Feed with cursors and dedupe (R1, R2, R6) | LitScout, or `summaries/` here (Q1) | Q1, Q2 answered; Phase 0 done |
| 2 | Record shape, summaries, keys optional (R3 to R5) | `summaries/` | Q3, Q4 answered |
| 3 | Page: source filter, links (R7, R8) | `js/`, `css/`, `index.html` | Q3, Q4 answered |
| 4 | Report (R9) and name (R10) | `summaries/digest.py`, page strings, README | Q6 answered; rows 1 to 3 merged |
