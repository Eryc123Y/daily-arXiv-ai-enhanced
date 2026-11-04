# Roadmap

Updated 2026-11-04 after aligning with the reader (Eric). The competitor comparison behind some items is in [competitive-brief.md](competitive-brief.md); the daily pipeline is described in [daily-pipeline.md](daily-pipeline.md).

## Direction

- **Who it is for**: Eric first, and soon something he can share. What sharing needs (a clear licence, labels, a fork that deploys cleanly) comes before the server. The radar and the project brief stay private in his vault.
- **Capacity**: Eric is in exams until 2026-11-16 and has no time for it before then. From 11-16 he has 3 hours or more a week, for decisions, reviews and trying new features; Claude does the building. Feature work stops in January for the ICML 2027 deadline (late January; check the official date).
- **Server**: a hosted service, Cloudflare Pages + D1 or Supabase (picked in the M2 spec), not the VPS. The `data` branch stays the source of truth, and `js/data-source.js` is the only page code that changes backend.

## Objectives and how they are measured

| Objective | Measure | Target | Where it is read |
|---|---|---|---|
| **The report is on time** | Weekdays with the report written by 11:30, among days arXiv announced by 10:00 | 90% or more | Sunday's health table (live since 11-03); an on-time count added in M0 |
| **The picks are worth reading** | Share of the report's picks Eric rates up or opens | A baseline in December, then up | Ratings, from M2 |
| **No important paper is missed** | Papers Eric or the Sunday search finds that should have been on the radar and were not | Zero at level high or medium, counted per month | A "missed" list, from M0 |

## Milestones

Status labels: **Done**, **On Track**, **Not Started**, **Needs Eric** (waits on a decision or an action only he can take).

### M0 · now to 2026-11-16 · no reader time

| Item | Owner | Status |
|---|---|---|
| Code links in the report, crawl times in the run log, Sunday health table, "arXiv has not announced yet" on the status line, a 16:20 catch-up run | Claude | **Done** (11-03, PR #22) |
| On-time count: Sunday's health table counts weekdays with the report by 11:30 | Claude | **Done** (11-04, PR #24) |
| Missed papers: `summaries missed` records Sunday look-back papers that were in an earlier batch in `missed.md`; the messenger appends the ones Eric points out | Claude (code, **Done** 11-04, PR #24); Eric pastes rule 5 of the messenger prompt | **Needs Eric** |
| Push notifications that reach the phone: cause found (a scheduled run is unattended and cannot turn Remote Control on); the messenger routine is the phone channel, and the run's last line says when the push was not sent | Claude | **Done** (11-04, docs only) |
| Sharing groundwork that needs no decision: summaries labelled as written from the abstract and failed loads shown as failures (both already done), the measured cost in the README, a guard that keeps vault files off the public branch | Claude | **Done** (11-04) |
| Specs for M1 and M2: [m1-shareable.md](specs/m1-shareable.md), [m2-reading-state-and-ratings.md](specs/m2-reading-state-and-ratings.md); open questions for Eric in each | Claude | **Done** (11-04) |
| Maintainability notes, [maintainability.md](maintainability.md): four decisions for Eric (types, module layout, record shapes, upstream leftovers) and fixes that need none | Claude | **Done** (11-04) |
| Messenger at 11:30 Sun-Fri, task model set to Sonnet, three idle routines deleted | Eric | **Needs Eric** |

### M1 · 2026-11-16 to 11-29 · shareable

| Item | Owner | Status |
|---|---|---|
| Licence: README already names upstream's Modified Apache License (section 9); Eric decides whether to ask upstream anything | Eric | **Needs Eric** |
| "Deploy your own" checked on a fresh fork end to end (needs Eric's OK to create a throwaway repository) | Claude | **Needs Eric** |
| A short shareable README and a link Eric can send | Claude; Eric approves | Not Started |
| Feedback from the first two weeks of reports folded into `feedback.md` | Eric 30 min, Claude summarises | Not Started |

### M2 · 2026-11-30 to 12-20 · reading state and ratings on a hosted backend

| Item | Owner | Status |
|---|---|---|
| Backend: Cloudflare Pages + D1 or Supabase, fed from the `data` branch after each push; one login for Eric | Claude; Eric creates the account | Not Started |
| Reading state: read/unread, star, read later, "since my last visit" | Claude | Not Started |
| Ratings: up or down on each paper, on the page and by reply in the messenger chat; the writer sees recent ratings; the hit-rate measure goes live | Claude | Not Started |
| Followed authors: a weekly line on Sunday's page | Claude | Not Started |

### M3 · 2026-12-21 to 2027-01-04 · finding more of the right papers

| Item | Owner | Status |
|---|---|---|
| Full-text search across all days, by topic, category and date | Claude | Not Started |
| Relevance beyond keywords: rank by similarity to starred and up-rated papers and to the project brief, next to keyword matches; judged against the hit rate | Claude | Not Started |
| Settings saved on the server (topics, keywords, followed authors, exclusions, schedule, models) | Claude | Not Started |

### Freeze · 2027-01-05 to the ICML deadline

Only fixes to the daily pipeline. Nothing that needs Eric's time.

## Dependencies and risks

- **M2 needs Eric to create the hosted account.** If that slips, M2 slips, and with it the hit rate.
- **Embedding ranking (M3) needs about a month of ratings** to be judged. If ratings are sparse, M3 ships search and settings, and ranking moves to Later.
- **arXiv and GitHub timing.** arXiv was about ten hours late on 2026-11-03 and GitHub skipped scheduled runs; the 16:20 run and the status line cover this.
- **Privacy.** The `data` branch is public. Radar reasons and ratings live in the vault or behind the login, never on the `data` branch.
- **Usage.** The pipeline runs on Eric's Claude plan; a usage gate at 80% hands the summaries to the API path (needs `ANTHROPIC_API_KEY`, not set).

## Later (after the ICML deadline)

- Other readers with their own topics on the same server, and a read-only JSON API.
- Notes per paper exported to Obsidian and Zotero/BibTeX; version watch for starred papers.
- Deep summary on demand for a starred paper, from the full PDF, cached.
- Trends: a topic-by-week chart and rising keywords.
- A status page with a re-run button and usage or API cost.
- The report's picks on the site, behind the login (they reveal the research direction).
- **Other sources come from a separate project.** Multi-source aggregation and an academic search MCP (OpenAlex or Crossref metadata; alphaXiv, Hugging Face, OpenReview, Semantic Scholar, GitHub, X and Reddit signals; publisher APIs such as Elsevier and IEEE Xplore with the reader's own keys for full text) are the job of **Ibid** ([Eryc123Y/ibid-mcp](https://github.com/Eryc123Y/ibid-mcp)), Eric's open-source scholar MCP planned on 2026-10-22: self-hosted on the user's Cloudflare account, v0.1 sources Semantic Scholar, OpenAlex, arXiv, OpenReview, CORE and a venue table; implementation after his exams. Publisher APIs are not in its v0.1 plan. This site does not build its own fetchers (Eric, 2026-11-04); once Ibid is ready, the pipeline reads its records, merged per paper by arXiv ID or DOI. Why it matters: [measurements/arxiv-coverage.md](measurements/arxiv-coverage.md) found that 62-85% of top ML and CV conference papers are on arXiv, but only 8-50% of IEEE, Elsevier and graphics journal papers and none of Journal of Vision, which is where much of the stereo and 3D-video work appears. Division of work from the 2026-11-02 measurements still holds: code fetches, dedupes and tags; a cheap model screens by meaning; one stronger model writes the report; full text only where the grade depends on it. Publisher abstracts are often copyrighted, so they are stored only behind the M2 login.

## Done

- 2026-11-03: one daily pipeline (crawl check from the Mac, headless Haiku summaries, a short Chinese report with deep links).
- 2026-11-03: Hugging Face Daily Papers upvotes as a second source.
- 2026-11-03: redesigned page with separate light and dark themes and a pipeline status line.
- 2026-11-03: code links in the report, a week health table, a 16:20 catch-up run.

## Deferred

- Intro video for the README, once the features and UI settle.
- AI triage from title and abstract (relevance, contribution type, evidence strength, confidence), sort only and never hide; undecided whether it can be done well, so only after a pilot on about 50 papers against Eric's own judgement.
- A daily email: the messenger routine and the push already deliver the report.

## Changes in this update

- Ordered by dated milestones tied to three objectives, instead of one ICE-ranked list.
- Sharing groundwork moved before the server (M0 and M1), because the goal is "Eric first, shareable soon".
- Server choice narrowed to a hosted service; the VPS is no longer a candidate.
- Added two measures that did not exist: the on-time count and the missed-papers list (M0).
- Ratings moved up with reading state into M2, because the hit-rate objective depends on them.
- With 3+ hours a week, search, ranking and server-side settings fit before January (M3); sharing with other readers on one server moved to Later.
