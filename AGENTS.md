# Notes for coding agents

Daily arXiv: a scheduled task on the maintainer's Mac crawls arXiv's `/new` listings into the `data` branch (`summaries ensure-day`, which also backfills missed days; no GitHub Actions schedule since 2026-11-09); summaries are written either by a local coding agent (default) or by an LLM API in Actions; the static site in this branch reads both. See README.md for the full picture.

## Layout

- `daily_arxiv/` Scrapy spider for the listings.
- `summaries/` Python package and CLI (`uv run python -m summaries --help`): data-branch publishing (`databranch.py`), the data files, run log and command output (`datafiles.py`), the GitHub CLI (`github.py`), summary merge rules (`records.py`), commands (`cli.py`), the local job (`local_runner.py`, with the work folder, lock and chunks in `localtask.py`), journal and conference papers from the feed command (`feed.py`, the venues in `watchlist.json`, matching in `dedupe.py`, local abstracts in `abstracts.py`), record shapes (`shapes.py`), the daily Chinese report (`digest.py`, Sunday's page in `weekly.py`, topic matching in `interests.py`), API providers (`providers.py`, `anthropic_api.py`, `openai_compat.py`, `llm.py`). Design and measurements of the daily pipeline: `docs/daily-pipeline.md`.
- `index.html`, `css/site.css`, `js/` the reading page. Data access goes through `js/data-source.js` only; which papers the list shows is `js/filters.js`; the two streams (arXiv by day, journals and conferences by week) are `js/streams.js`; the date picker is `js/calendar.js` (logic) and `js/calendar-picker.js` (the popover), and the oldest day offered is `EARLIEST_DAY` in `js/data-config.js` (2025-12-29; the inherited upstream days stay on the data branch but are hidden).
- `wrangler.jsonc` and `scripts/build_site.py` host the page on Cloudflare (see Deployment); `summaries/sites.json` is the page's address for report links.
- `tests/` pytest suite and `tests/js/` node tests. `conftest.py` at the root stops any test from reaching GitHub, the network or the real remote.
- Only `__main__.py` imports `cli`; shared helpers go in `datafiles.py`, `github.py` or `localtask.py`, so modules never import each other in a cycle.

## Working on the code

- Checks: `scripts/check.sh` runs both type checkers, ruff and both test suites (`uv run pytest -q`, `node --test tests/js/*.test.js`), stopping at the first failure. Write the failing test first. No CI runs (Actions is disabled on the repository), so run it before merging.
- Types: the page's JS is typed with JSDoc and checked by `tsc --checkJs` (`tsconfig.json`, strict, no emit); there is no build step, the browser runs the files as written. Record shapes are in `js/types.js`, the globals the scripts share in `js/globals.d.ts`, `app.js`'s state and elements in `js/app-state.d.ts`. Python is checked by pyright (basic; strict for the modules listed in `pyproject.toml`) and ruff.
- Record shapes are written twice, `summaries/shapes.py` and `js/types.js`; change both together. `tests/test_shapes_parity.py` fails when a field or shape is on one side only.
- Commits: `<type>: <description>` (feat, fix, refactor, docs, test, chore), no attribution lines, identity `Eryc123Y <145822832+Eryc123Y@users.noreply.github.com>`.
- After changing anything under `js/` or `css/`, bump every `?v=` in `index.html`, or browser and CDN caches serve the old file. A new file the page loads must also be added to the allowlist in `scripts/build_site.py` (`tests/test_build_site.py` fails otherwise).
- Never edit the `data` branch by hand or check it out; the CLI commits to it with git plumbing. `.cache/` is local scratch and is not committed.
- Never read, print or store API keys.

## Deployment

The page is served by Cloudflare at https://litscout.turing2234.com/, not GitHub Pages. GitHub Actions are not used.

- Host: Cloudflare Workers static assets. Worker `litscout-daily`, configured by `wrangler.jsonc` (serves `./dist`, custom domain `litscout.turing2234.com`, no `workers.dev` address).
- Build: `python3 scripts/build_site.py` copies an allowlist of public page files into `dist/` (gitignored). Deploy: `npx wrangler deploy`.
- Automatic deploy: Cloudflare Workers Builds runs the build and deploy commands on every push or merge to `main`. Do not deploy from a feature branch.
- Manual fallback: on an up-to-date `main`, `python3 scripts/build_site.py && npx wrangler deploy` (needs `npx wrangler login` on that machine).
- To check a deploy: Cloudflare dashboard → Workers & Pages → `litscout-daily` → Deployments, or `npx wrangler deployments list`; then confirm https://litscout.turing2234.com/ returns 200.
- Do not rename the Worker (`name` in `wrangler.jsonc`); a new name creates a separate Worker without the domain.
- The `litscout.turing2234.com` DNS record is managed by the Worker custom domain. Do not add a manual DNS record for it.
- Data is not deployed: the page reads the `data` branch from raw.githubusercontent.com. `index.html` redirects the old address `eryc123y.github.io/daily-arXiv-ai-enhanced/` here; GitHub Pages still serves `main` for that.

## Writing the day's summaries

When asked to write or catch up the daily summaries, run the job with your own client's headless mode:

```bash
uv run python -m summaries run-local --client codex
```

`--client` is `claude`, `codex`, `antigravity`, or `custom` with `--command '["cli","-p","{prompt}"]'`. Add `--model` to pick a model and `--max-chunks N` to cap how much one run spends. The job merges and pushes as it goes, so a stopped run resumes on the next one.

To do it inside an interactive session instead (for example with subagents):

1. `uv run python -m summaries status --days 4` lists days with pending papers.
2. `uv run python -m summaries prepare --date D` writes `INSTRUCTIONS.md` and chunk files and prints them (exit code 3: another run holds the lock; stop).
3. For each chunk, read `INSTRUCTIONS.md` and write the output file it describes for that chunk's input, yourself or with a subagent per chunk.
4. `uv run python -m summaries merge --date D` after every few chunks and at the end.
5. `uv run python -m summaries record --date D --path local-<client>`, then `uv run python -m summaries finish`.
