# Spec: shareable (M1)

Status: draft, 2026-11-04. Milestone M1 in [ROADMAP.md](../ROADMAP.md), planned 2026-11-16 to 11-29.

## Problem

Eric wants to send the site to classmates or his group soon. Someone who opens the link should understand in a minute what it is and what it is not, and someone who wants their own copy should get one running without asking him.

## Goals

1. A first-time visitor can tell from the page and the README that the summaries are AI-written from abstracts, and where the code and licence are.
2. A person with a GitHub account and uv can deploy their own copy by following the README, with no help, in under 30 minutes.
3. Nothing private (radar, project brief, ratings) is visible on Eric's public instance.

## Non-goals

- Accounts for other people on Eric's instance (Later).
- A landing page or promo video (Deferred).
- Support for summary providers other than the ones already built (Anthropic, OpenAI-compatible, Gemini, local agents).

## State on 2026-11-04

| Requirement | State |
|---|---|
| README states the licence correctly (upstream's Modified Apache License, section 9) | done before M1 |
| The page says summaries are written from abstracts | done before M1 (reader footer) |
| A failed download is shown as a failure, not an empty day | done before M1 (`LoadError`, retry button) |
| README states what a day costs | done 11-04 |
| "Deploy your own" verified on a fresh fork end to end | not done: needs a new public repository, so Eric's OK first |
| A short "what this is" paragraph at the top of the README, written for a classmate | not done |
| Private files stay off the public instance | holds today; to be re-checked with M2's state |

## Requirements

- **R1** Fresh-fork test: fork to a throwaway repository (Eric's account or a second one), run the README steps verbatim, record every step that needed more than the README said, and fix the README or `summaries setup`. Acceptance: a second run from the fixed README needs no extra step.
- **R2** README opening: three sentences on what the site does, a screenshot, and the live link. Acceptance: Eric reads it and would send it as is.
- **R3** A privacy check in CI: a test that the publishing commands never write `project-brief.md`, `project-radar.md`, `feedback.md`, `missed.md` or rating files to the `data` branch.

## Open questions

| # | Question | For | Blocking |
|---|---|---|---|
| Q1 | May I create a throwaway fork on your GitHub account for R1 (deleted afterwards), or do you prefer a second account? | Eric | yes, for R1 |
| Q2 | Is upstream's licence clear enough to share, or do you want to ask dw-dengwei first? | Eric | no |
