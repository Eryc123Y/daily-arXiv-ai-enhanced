# Roadmap

Now / Next / Later, updated 2026-11-03. **Now** is what can be done without the reader's time while he is in exams (to 2026-11-16). **Next** starts after that and mostly needs the server: a VPS, or Cloudflare Pages + D1 / Supabase. **Later** is direction, not commitment. The pipeline keeps the `data` branch as the source of truth, and `js/data-source.js` is the only page code that changes backend.

Items are ranked by ICE (Impact, Confidence, Ease; 1-10 each, score = I × C × E / 100). The site has one reader, so RICE's reach does not apply. Impact means time saved or papers not missed for that reader. The competitor comparison behind some items is in [competitive-brief.md](competitive-brief.md).

## Now (November, no reader time needed)

| Item | I | C | E | ICE | State |
|---|---|---|---|---|---|
| Code links in the report and a `[code]` hint to the writer | 6 | 9 | 9 | 4.9 | done 11-03 |
| Pipeline health: crawl entries in the run log, a health table on Sunday's page, "arXiv has not announced yet" on the status line | 6 | 8 | 8 | 3.8 | done 11-03 |
| A 16:20 run for late announcements | 7 | 8 | 10 | 5.6 | done 11-03 |
| Push notifications that reach the phone: the 11-03 push failed with Remote Control disconnected; find out why and fall back to the messenger chat | 7 | 5 | 6 | 2.1 | open |
| Weekly synthesis of `feedback.md` and the messenger chat into the writer's standing preferences | 5 | 6 | 7 | 2.1 | open |

## Next (from mid-November)

| Item | I | C | E | ICE |
|---|---|---|---|---|
| **Reading state**: read/unread, star, "read later", "since my last visit" | 8 | 8 | 5 | 3.2 |
| **Followed authors** as a weekly line on Sunday's page | 4 | 8 | 8 | 2.6 |
| **Ratings as a signal**: a thumbs up or down per paper (on the page, or by replying in the messenger chat); the writer sees recent ratings, and later they train the ranking (as Scholar Inbox and arxiv-sanity do) | 8 | 6 | 5 | 2.4 |
| **Full-text search across all days** with filters by topic, category and date range | 6 | 8 | 5 | 2.4 |
| **Server backend**: the two calls of `js/data-source.js` (list days, load a day), a database fed from the `data` branch after each push, one login | 7 | 8 | 4 | 2.2 |
| **Settings saved on the server**: summary mode and model, usage threshold, schedule; arXiv categories; topics, keywords, followed authors, exclusion keywords (`disparity` only with `stereo`); main paper link and theme; notification content | 6 | 8 | 4 | 1.9 |
| **Relevance beyond keywords**: embedding similarity to starred papers and to the project brief, next to keyword matches | 8 | 6 | 4 | 1.9 |

Dependencies: reading state, ratings and settings need the server; embedding ranking needs ratings or stars to learn from.

## Later

- **Notes per paper**, exported to Obsidian and Zotero/BibTeX; **version watch** for starred papers.
- **Deep summary on demand** for a starred paper, from the full PDF, cached.
- **Trends**: a topic-by-week chart and rising keywords, replacing upstream's statistic page.
- **Status page** with a re-run button and usage or API cost (the status line and Sunday's health table cover the basics now).
- **Sharing**: other readers with their own topics, and a read-only JSON API.
- **Many sources, one daily view.** Each source is fetched by code on a schedule and merged into one record per paper (arXiv ID, else DOI):
  - alphaXiv trending and discussion counts, and Hugging Face models and datasets (upvotes already done);
  - OpenReview reviews and decisions;
  - Semantic Scholar or OpenAlex: citations, new papers by followed authors, who cites the radar papers;
  - GitHub stars for linked code;
  - X and Reddit discussion through an agent-reach style fetcher;
  - conference accepted-paper lists, blogs and lab pages through RSS.

  Division of work, from the 2026-11-02 measurements (docs/daily-pipeline.md): code fetches, dedupes and tags; a cheap model screens by meaning; one stronger model writes the short report; full text only for the few papers whose grade depends on it.
- **Our own papers MCP server**: the database behind the site as MCP tools (search by topic, date and keyword; read a summary; list the radar), so any Claude session can ask what came out on a topic without a crawl.

## Done

- 2026-11-03: one daily pipeline (crawl check from the Mac, headless Haiku summaries, a short Chinese report with deep links; docs/daily-pipeline.md).
- 2026-11-03: Hugging Face Daily Papers upvotes as a second source (`signals.yml`, ▲ on the page, a line in the report).
- 2026-11-03: redesigned page with separate light and dark themes, a pipeline status line, code links in the report, a week health table, and a 16:20 catch-up run.

## Deferred

- Intro video for the README, once the features and UI settle.
- AI triage from title and abstract (undecided whether it can be done well): relevance to the reader's topics (0-3), contribution type, strength of the evidence the abstract states, whether it explains mechanisms or conditions, code and compute needs, and the model's confidence in each judgement, written in the same call as the summary. Sort only, never hide; pilot on about 50 papers against the reader's own judgement first. No author or venue prestige, no citation forecasts, no novelty verdicts from abstracts.
- A daily email: the messenger routine and the push already deliver the report.
