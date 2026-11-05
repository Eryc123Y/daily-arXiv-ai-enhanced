# Spec: reading state and ratings (M2)

Status: draft for Eric to decide, 2026-11-04. Milestone M2 in [ROADMAP.md](../ROADMAP.md), planned 2026-11-30 to 12-20. The questions marked **blocking** need answers before any code; the rest can be settled while building.

## Problem

Eric reads the report on his phone in the morning and opens papers on the site from the Mac and the phone. The site forgets everything between devices and visits: which papers he has read, which he wants to come back to, and which picks were worth it. The pipeline gets no signal about its picks except `feedback.md` (two lines after a month), so it chooses from keywords and the project brief alone and cannot measure the second objective in the roadmap, "the picks are worth reading". Every competitor that learns the reader's taste (Scholar Inbox, arxiv-sanity, Semantic Scholar feeds) does it from ratings ([competitive-brief.md](../competitive-brief.md)).

## Goals

1. Eric's read, starred and read-later marks are the same on the Mac and the phone within a minute.
2. Rating a paper takes one tap on the page, or one short reply in the messenger chat.
3. The pick hit rate (share of the report's picks rated up or opened) is computed every Sunday from the start of M2.
4. The report writer sees the last four weeks of ratings, so its picks can follow them.
5. A fork without the backend works exactly as today.

## Non-goals

- **Other readers on the same server.** One login, Eric's. Sharing is "deploy your own" (M1); multi-reader is Later.
- **Ranking by embeddings.** M3, and only once there are about a month of ratings to judge it by.
- **Settings on the server.** M3. Topics and keywords stay in the browser and in `js/interest-presets.js` for now.
- **Public ratings or counts.** Ratings reveal the research direction, so they never go on the public `data` branch.
- **Notes per paper.** Later; a note is a different object with its own export story.

## User stories

1. As Eric reading on the phone, I want to star a paper so that I find it on the Mac in the evening.
2. As Eric, I want "since my last visit" to show only papers that came in after I last opened the site, so that I do not re-scan days I have read.
3. As Eric, I want a "read later" list across days, so that a paper I could not read today does not get lost in tomorrow's batch.
4. As Eric reading the report in the messenger chat, I want to reply "👍 2611.02529" or "这篇没用 2611.00319", so that I can rate without opening the site.
5. As Eric on Sunday, I want to see what share of the week's picks I found worth it, so that I know whether the report is improving.
6. As Eric with no connection, I want my marks to be kept and sent later, so that a tap is never lost. (Edge case.)
7. As someone who forked the site, I want it to work without any backend, so that I am not forced to set one up. (Edge case.)

## Requirements

### P0 (M2 does not ship without these)

| # | Requirement | Acceptance criteria |
|---|---|---|
| R1 | **Login for one person.** The backend accepts only Eric. | Given a browser that is not logged in, when it calls the state API, then it gets 401 and the page shows the reading features as off, not broken. |
| R2 | **Reading state per paper**: read (set on opening the reading pane), starred, read later; with the time each changed. | Given Eric stars a paper on the phone, when he opens the site on the Mac within a minute, then the star is there. Unstarring removes it on both. |
| R3 | **Ratings per paper**: up, down or none, from the page. | One tap sets up or down; a second tap on the same clears it. The rating shows next to the title in the list. |
| R4 | **Ratings from the messenger chat.** The messenger appends `- YYYY-MM-DD: <id> up|down <optional words>` to `DIGEST/ratings.md`; the pipeline merges it with the page's ratings, newest wins. | Given Eric replies "👍 2611.02529", then `ratings.md` gains one line and the next Sunday counts it. |
| R5 | **The writer sees ratings.** `digest` adds the last 28 days of rated papers (title, up or down) to the writer prompt. | The prompt contains a "Recent ratings" section; a test checks its format and that it is capped (at most 60 lines). |
| R6 | **Hit rate on Sunday's page.** For the week's picks (`picks.json`): rated up, or opened from the report, divided by all picks. | A test with known picks and ratings gives the expected fraction; days without picks are not counted. |
| R7 | **Optional backend.** The page detects the backend; without it the reading features are hidden and nothing else changes. | The existing node tests pass unchanged with no backend configured. |
| R8 | **Private.** Ratings and reading state never reach the public `data` branch or the public site files. | A test of the publishing code asserts no state file is written there. |

### P1 (fast follow)

- "Since my last visit" view: papers added after the last time the page was opened on any device.
- "Opened from the report" as its own signal: report links carry `&from=report`, and opening such a link records it (feeds R6 without a rating).
- Offline queue: marks made without a connection are kept in the browser and sent when it returns (story 6).
- Export: a JSON download of all state, so it is never locked into one service.

### P2 (design for, do not build)

- More readers with their own state (Later): every row carries a reader id from the start, even though there is one.
- Embedding ranking (M3): ratings are stored per paper id with the paper's day, so a later job can join them to summaries.
- Settings on the server (M3): the same login and API host.

## Design sketch (for the blocking questions)

- **Where the state lives.** A new `js/state-source.js` beside `js/data-source.js`, with two implementations: `remote` (the backend) and `none` (no backend: every call answers "unavailable"). The paper data stays on the `data` branch; only state moves.
- **Records** (an event log, decided in Q3; field types settle with D1/D3):
  - `paper_event(reader, paper_id, day, kind, value, at, source)`: one row per tap. `kind` is `read`, `star`, `later` or `rating`; `value` is `on`/`off` for the first three and `up`, `down` or `none` for `rating`; `source` is `page` or `chat`.
  - `paper_state`: a view with the latest value of each kind per paper, which is what the page reads.
  - `visit(reader, at)` for "since my last visit".
- **API**, same origin as the page: `GET /api/state?since=<time>` returns changed rows; `PUT /api/state/<paper_id>` sets fields; both behind the login.
- **The pipeline reads ratings** through one read-only call with a token kept in the macOS keychain (never in the repository or a log), merged with `DIGEST/ratings.md`.

## Decisions (Eric, 2026-11-05)

| # | Question | Decision |
|---|---|---|
| Q1 | Cloudflare (Pages Functions + D1, login through Cloudflare Access) or Supabase? | **Cloudflare.** Access means no login code, D1 is SQLite and easy to test locally, and LitScout is planned on Cloudflare too. Eric's instance moves from GitHub Pages to Cloudflare Pages. |
| Q2 | Page code in TypeScript (a build step) or JSDoc checked by `tsc --checkJs`? | **JSDoc with `tsc --checkJs`**, no build step, so a fork deploys as it is. |
| Q3 | One row per paper, or an event log? | **Event log** (see Records): the hit rate and M3 ranking need the history, and the volume is a few hundred taps a week. |
| Q4 | What counts as "read"? | Opened in the reading pane. |
| Q5 | Does a down rating hide a paper? | No: it marks the paper and sorts it lower; the list never hides papers. |
| Q6 | Rating from the messenger chat | "👍/👎 + arXiv ID"; the messenger also accepts free text and repeats what it understood for Eric to confirm. |

## Timeline

- 11-30: Eric creates the Cloudflare account (about 15 minutes); Q1-Q3 were answered on 11-05.
- 12-01 to 12-07: backend, login, `state-source.js`, R1, R2, R7, R8.
- 12-08 to 12-14: ratings on the page and from the chat (R3, R4), writer prompt (R5).
- 12-15 to 12-20: hit rate on Sunday's page (R6), P1 items as time allows.
- Risk: if the account is not ready by 12-01, the backend slips; R4 and R5 can still ship first, from `ratings.md` alone.
