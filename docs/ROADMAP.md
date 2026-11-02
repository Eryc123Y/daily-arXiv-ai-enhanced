# Roadmap

Planned for after the move from GitHub Pages to a self-hosted server (a VPS, or Cloudflare Pages + D1 / Supabase), from mid-November 2026 at the earliest. The pipeline keeps the `data` branch as the source of truth; the server adds a database for settings and per-reader state. `js/data-source.js` is the only page code that changes backend.

## Phase 1: server and settings (first)

- **Server backend**: an API with the same two calls as `js/data-source.js` (list days, load a day), a database fed from the `data` branch after each crawl and summary push, and a login (one owner; more readers later).
- **Settings page**, saved on the server so every device sees the same thing:
  - summaries: mode (local agent or API), provider and model, effort, language, usage-gate threshold, schedule times;
  - crawl: arXiv categories;
  - interests: topics with their keywords and colours, authors to follow, and exclusion keywords (for example `disparity` only together with `stereo`, to keep fairness papers out);
  - reading: the main paper link (alphaXiv by default, arXiv, or PDF), default topic, light/dark/system theme;
  - notifications: on or off per day type, what the daily push includes.
- **Reading state**: read/unread, star, "read later" queue, and a "since my last visit" view.

## Phase 2: finding the right papers

- **Full-text search across all days** (title, abstract, summaries), with filters by topic, category and date range.
- **Relevance beyond keywords**: rank papers by embedding similarity to starred papers and to the project brief, shown next to keyword matches.
- **Notes per paper**, exported with the paper to Obsidian (a note with title, link, summary and your note) and to Zotero/BibTeX.
- **Version watch**: notify when a starred paper gets a new arXiv version.

## Phase 3: depth and overview

- **Deep summary on demand**: for a starred paper, a longer summary from the full PDF (method details, experiments, limitations), cached.
- **Trends**: a topic-by-week chart and rising keywords, replacing upstream's statistic page.
- **Status page**: last crawl and summary runs, per-day progress, failures with a re-run button, and usage or API cost.
- **Sharing**: other readers with their own topics on the same server, and a read-only JSON API.

## Phase 4: many sources, one daily view (long term)

Today the pipeline reads one source, arXiv's `/new` listings. The long-term plan is to gather what matters to the reader from several platforms each day and hand them one short report.

- **Sources**, each fetched by code on a schedule and merged into one record per paper (keyed by arXiv ID, else DOI):
  - Hugging Face Daily Papers and alphaXiv trending: community attention (upvotes, discussion);
  - OpenReview: reviews, scores and decisions for conference submissions;
  - Semantic Scholar or OpenAlex: citations, new papers by followed authors, and who cites the papers on the radar;
  - GitHub: code release and stars for linked repositories;
  - X and Reddit (r/MachineLearning): discussion around a paper, through an agent-reach style fetcher;
  - conference accepted-paper lists (CVPR, NeurIPS, ICML, ICLR), blogs and lab pages through RSS.
- **Division of work**, from the 2026-11-02 measurements (docs/daily-pipeline.md): code fetches, dedupes and tags; a cheap model screens by meaning; one stronger model writes the short report; full text only for the few papers whose grade depends on it.
- **Our own papers MCP server**: the database behind the site exposed as MCP tools (search papers by topic, date and keyword; read a paper's summary; list the radar), so any Claude session can ask "what came out this week on X" or "what on the radar collides with my project" without a crawl.
- Needs the Phase 1 server and database; the static site keeps working on the `data` branch until then.

## Done since the roadmap was written

- 2026-11-03: one daily pipeline (crawl check from the Mac, headless Haiku summaries, a short Chinese report with deep links; docs/daily-pipeline.md).
- 2026-11-03: first second source, Hugging Face Daily Papers upvotes (`signals.yml`, ▲ badges on the page, a line in the report).

## Deferred

- Intro video for the README, once the features and UI settle.
- AI triage from title and abstract (undecided whether it can be done well): relevance to the reader's topics (0-3), contribution type, strength of the evidence the abstract states, whether it explains mechanisms or conditions, code and compute needs, and the model's confidence in each judgement, written in the same call as the summary. Sort only, never hide; pilot on about 50 papers against the reader's own judgement first. No author or venue prestige, no citation forecasts, no novelty verdicts from abstracts.
