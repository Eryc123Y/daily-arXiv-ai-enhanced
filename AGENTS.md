# Notes for coding agents

Daily arXiv: GitHub Actions crawls arXiv's `/new` listings into the `data` branch; summaries are written either by a local coding agent (default) or by an LLM API in Actions; the static site in this branch reads both. See README.md for the full picture.

## Layout

- `daily_arxiv/` Scrapy spider for the listings.
- `summaries/` Python package and CLI (`uv run python -m summaries --help`): data-branch publishing (`databranch.py`), summary merge rules (`records.py`), the local job (`cli.py`, `local_runner.py`), API providers (`providers.py`, `anthropic_api.py`, `openai_compat.py`, `llm.py`).
- `index.html`, `css/site.css`, `js/` the reading page. Data access goes through `js/data-source.js` only.
- `tests/` pytest suite and `tests/js/` node tests.

## Working on the code

- Tests: `uv run pytest -q` and `node --test tests/js/*.test.js`. Write the failing test first.
- Commits: `<type>: <description>` (feat, fix, refactor, docs, test, chore), no attribution lines, identity `Eryc123Y <145822832+Eryc123Y@users.noreply.github.com>`.
- After changing anything under `js/` or `css/`, bump every `?v=` in `index.html`, or GitHub Pages' cache serves the old file.
- Never edit the `data` branch by hand or check it out; the CLI commits to it with git plumbing. `.cache/` is local scratch and is not committed.
- Never read, print or store API keys.

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
