# Roadmap

Planned for after the move from GitHub Pages to a self-hosted server (a VPS, or Cloudflare Pages + D1 / Supabase). The pipeline keeps the `data` branch as the source of truth; the server adds a database for settings and per-reader state. `js/data-source.js` is the only page code that changes backend.

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

## Deferred

- Intro video for the README, once the features and UI settle.
