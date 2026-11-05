# Maintainability notes

A running list of what would make the code harder to keep correct as it grows, with a suggested fix and whether it needs a decision from Eric. Started 2026-11-04 from a read of the repository and a Codex (`gpt-6-astra`, high effort) review of PR #24. Items are removed when fixed.

## Decisions (architecture and types)

Eric decided D1-D4 on 2026-11-05, taking the recommendations below. The observations that led to them are in the git history of this file.

| # | Observation | Decision | State |
|---|---|---|---|
| D1 | **No types are checked**: none of the 154 functions in `summaries/` has annotations, and there is no type checker or linter; the page is plain JS. Record-shape changes are caught only by tests that happen to cover them. | Python: pyright in basic mode and ruff in CI; strict for new modules, annotations added module by module. JS: JSDoc types checked by `tsc --checkJs`, no build step (same answer as Q2 in the M2 spec). | M1 |
| D2 | **`cli.py` is both the entry point and a library**: `digest`, `weekly`, `signals`, `missed` import it for shared helpers, and `cli.main` imports them back inside the function to avoid a cycle. | Move the shared pieces (paths, `read_records`, the run log, `emit`) to `summaries/datafiles.py`; `cli.py` keeps argument parsing and commands. One mechanical PR. | M0 |
| D3 | **Record shapes are implicit**: the raw paper, summary record, run-log entry, `picks.json` and radar row are dicts built and parsed in several places, in Python and JS. | A `TypedDict` per record in `summaries/shapes.py` (types only, no runtime change), a JSDoc `@typedef` per record in `js/types.js`, and a schema table in the docs. With D1. | M1 |
| D4 | **Upstream leftovers**: `ai/`, `to_md/`, `update_readme.py`, the templates, `run.sh`, `SKILL/`, the auth files, about 5,000 lines no workflow or page uses. | Delete them in one PR; upstream parity is no longer a goal. Keep `statistic.html` (Keyword trends) until the M3 Trends item replaces it. | M0 |

## Can be fixed without a decision

| # | Observation | Suggestion | State |
|---|---|---|---|
| F1 | **Keyword matching exists twice**, in `js/paper-data.js` and `summaries/interests.py`, kept in step by hand; the report's topic counts and the page's must agree. | One table of match cases (keyword, text, expected) in `tests/fixtures/keyword-cases.json`, run by both the node and the Python suites. | done in this PR |
| F2 | **The Python side reads topics from `js/interest-presets.js` with a regex.** A formatting change in the JS file (double quotes, a trailing comment) silently drops a topic from the report. | A test that the Python parser finds every topic the JS file defines (count and names), run in both suites; later, move the presets to JSON. | done in this PR (test) |
| F3 | **Nothing stopped a private file from being published.** The `data` branch is public, and the radar, brief, feedback, missed list, reports and digest cache must never reach it. | `DataBranch.publish` accepts only the file kinds the page reads (a day's papers, summaries and upvotes, the run log, two asset files) and refuses anything else, with a test per private kind. A first version with a list of private names missed `data/picks.json` and `data/digests/*.md` (found by the Codex review). | done in this PR |
| F4 | **The project-page pattern is defined three times**: the spider, `js/render.js` and `summaries/digest.py`. | Store `code_kind` (`code` or `page`) in the record at crawl time, so readers do not re-derive it. Small, but it changes the data format, so with D3. | open |
| F5 | **`digest.py` is 616 lines** and holds candidate building, prompts, answer parsing, full-text fetching, rendering and file writes. | Split along those lines (`digest/candidates.py`, `prompts.py`, `render.py`) when it next grows; the functions are already short and pure, so the split is mechanical. | open |
| F7 | **`missed.md` and the radar table are parsed as Markdown** with a fixed column order, and look-back rows are recognised by "回溯" in the level column; a hand edit that reorders columns is skipped without a warning. | Keep the structured record (JSON lines) as the source and render the Markdown from it. For now `summaries missed` lists the rows it cannot read (`skipped` in its output, a warning on stderr) and leaves them out of the counts. | warning done 11-05; JSON source open |
| F6 | **Some tests reach the network or the real data branch unless told not to** (`digest-week` reads the run log; two tests now stub it). | `conftest.py` at the repository root, loaded before collection for every test directory, sets `GIT_ALLOW_PROTOCOL=file` (git then refuses the real https remote by any route) and refuses `gh`, `curl`, `wget`, non-local DNS lookups and connections, with a message saying what to stub. | done 11-05 |

## Things that are in good shape

- Functions are short: only `build_parser` in `cli.py` is over 50 lines.
- The data access of the page goes through one module (`js/data-source.js`), so the backend can change without touching the views.
- Each bug fixed in the last week came with a test that failed first; 168 Python and 57 JS tests run in under a minute in CI.
