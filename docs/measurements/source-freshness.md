# How fresh non-arXiv sources are (2026-11-11)

Question (spec S1, R0): for each venue of [Watch list v1](../specs/s1-sources-beyond-arxiv.md#watch-list-v1-q2), how many days after publication do OpenAlex, Crossref and OpenReview first list a paper, how many papers a day would a feed add, and how many of them match Eric's topics?

## Method

- Window: the 14 days 2026-10-29 to 2026-11-11. A paper is **new** when the source first listed it in the window: OpenAlex `created_date`, Crossref `created` (the publisher's DOI registration).
- **OpenAlex**: every work of each venue (`primary_location.source.id`) with a publication date from 2025-11-11 on, 200 a page, only the fields needed. The free plan refuses `from_created_date` ("part of daily sync, Member+ and Partner plans"), so the script pages through a year of publication dates and keeps the works created in the window. Works published before 2025-11-11 are not seen.
- **Crossref**: each journal by ISSN with `from-created-date` in the window (the brief named `from-pub-date`; a 14-day publication window cannot show delays, and Crossref has no quota, so the feed-shaped query was used). ECCV, which OpenAlex files under Lecture Notes in Computer Science, by its container title "Computer Vision – ECCV 2026".
- **OpenReview** API v2 for ICLR, ICML, NeurIPS and TMLR: **not measured**. Every anonymous request from the script got `403 ChallengeRequiredError` (a browser challenge), so it was not retried. The script takes `OPENREVIEW_TOKEN` for a logged-in rerun.
- **Delay** = listing date minus publication date, from records with a reliable publication date only. IEEE journals give no usable day (see "Unreliable dates"), so for journals the note also measures **OpenAlex's lag behind the DOI registration**: OpenAlex `created_date` minus Crossref `created` of the same DOI.
- **Conferences** list nothing day by day, so a second check takes a 200-work sample of each conference's latest proceedings in OpenAlex and reads its publication and listing dates.
- **Topics**: the matcher the site uses (`summaries/interests.py`, Eric's four topics), over title plus abstract. A record without an abstract can match on its title only.
- **Already on the site**: arXiv ID, or the exact normalised title, against the 6,434 papers in the last 60 days of `data/<date>.jsonl` on `origin/data`. A paper renamed between its arXiv and journal versions is not caught.
- Script: [source_freshness.py](source_freshness.py). Raw responses are in `.cache/freshness/<date>/` (not committed). Run with `OPENALEX_API_KEY` set; it stops cleanly and summarises what it has if OpenAlex quota runs out.

## Result: the 14-day window

"(n<20)" marks venues with fewer than 20 new papers: read those shares as rough. Papers per day is new papers divided by 14. Delay is in days.

| Source | Venue | New in 14 d | Per day | Topic matches | Delay median / p90 | Reliable dates | Abstract | OA link | arXiv version | Already on site |
|---|---|---|---|---|---|---|---|---|---|---|
| OpenAlex | ACM MM | 846 | 60.4 | 81 | 1 / 1 | 841 | 96% | 100% | 1% | 13 |
| OpenAlex | ACM TOG | 53 | 3.8 | 2 | 1 / 1 | 51 | 100% | 100% | 8% | 5 |
| OpenAlex | IEEE TVCG | 53 | 3.8 | 4 | - | 0 | 100% | 96% | 0% | 1 |
| OpenAlex | CGF (n<20) | 4 | 0.3 | 0 | 1 / 1 | 4 | 100% | 75% | 0% | 0 |
| OpenAlex | IEEE TPAMI | 28 | 2.0 | 4 | - | 0 | 96% | 96% | 14% | 7 |
| OpenAlex | IJCV (n<20) | 9 | 0.6 | 2 | 2 / 6 | 9 | 11% | 11% | 0% | 0 |
| OpenAlex | IEEE TIP (n<20) | 19 | 1.4 | 0 | - | 0 | 95% | 79% | 0% | 0 |
| OpenAlex | IEEE TCSVT | 62 | 4.4 | 4 | 1 / 1 (3 papers) | 3 | 94% | 90% | 0% | 0 |
| OpenAlex | Journal of Vision (n<20) | 3 | 0.2 | 1 | 1 / 1 | 3 | 100% | 100% | 0% | 0 |
| OpenAlex | CVPR, ICCV, NeurIPS, ICML, ICLR, AAAI, IJCAI, JMLR, TMLR (n<20) | 0 | 0 | 0 | - | - | - | - | - | - |
| Crossref | ACM TOG | 98 | 7.0 | 8 | 0 / 0 | 98 | 100% | 100% | 0% | 5 |
| Crossref | IEEE TVCG | 75 | 5.4 | 1 | - | 0 | 0% | 7% | 0% | 1 |
| Crossref | CGF (n<20) | 6 | 0.4 | 0 | 0 / 0 | 6 | 100% | 33% | 0% | 0 |
| Crossref | IEEE TPAMI | 49 | 3.5 | 2 | - | 0 | 0% | 4% | 0% | 7 |
| Crossref | IJCV (n<20) | 17 | 1.2 | 2 | 0 / 1 | 17 | 6% | 6% | 0% | 0 |
| Crossref | IEEE TIP | 24 | 1.7 | 0 | - | 0 | 0% | 0% | 0% | 0 |
| Crossref | IEEE TCSVT | 71 | 5.1 | 2 | - | 0 | 0% | 1% | 0% | 0 |
| Crossref | Journal of Vision (n<20) | 5 | 0.4 | 0 | 0 / 0 | 5 | 0% | 100% | 0% | 0 |
| Crossref | JMLR, TMLR, ECCV (n<20) | 0 | 0 | 0 | - | - | - | - | - | - |

Crossref's "OA link" is a Creative Commons licence on the record, and its "arXiv version" is a `has-preprint` relation, which these publishers do not deposit; both read low for that reason. OpenAlex's shares come from `open_access.oa_url` and an arXiv location.

### Journals: OpenAlex behind the DOI registration

For the 231 journal works OpenAlex listed in the window, every one has a Crossref record. Days from DOI registration to OpenAlex listing:

| Venue | OpenAlex new | Lag median / p90 | Crossref new | of which in OpenAlex by 11-11 |
|---|---|---|---|---|
| ACM TOG | 53 | 1 / 1 | 98 | 97 |
| IEEE TVCG | 53 | 1 / 1 | 75 | 75 |
| CGF (n<20) | 4 | 1 / 1 | 6 | 6 |
| IEEE TPAMI | 28 | 1 / 1 | 49 | 47 |
| IJCV (n<20) | 9 | 1 / 1 | 17 | 14 |
| IEEE TIP (n<20) | 19 | 1 / 1 | 24 | 23 |
| IEEE TCSVT | 62 | 1 / 1 | 71 | 70 |
| Journal of Vision (n<20) | 3 | 1 / 1 | 5 | 5 |

So OpenAlex lists a journal paper one day after its DOI exists, and 337 of the 345 DOIs Crossref registered in the window were in OpenAlex by 11-11. But Crossref has 345 new and OpenAlex only 231 "created" in the window: the other ~110 are in OpenAlex under an **older** `created_date`, because OpenAlex merged the journal version into a work it already had (usually the arXiv preprint). An OpenAlex feed keyed on `created_date` would therefore miss exactly the journal versions of arXiv papers; the feed has to key on publication date or on DOIs from Crossref.

### Conferences: when proceedings appear

Conferences do not trickle; their proceedings appear as one batch, months after the meeting for some.

| Proceedings | Source | Sample | Reliable dates | Delay median / p90 | Publication date | Listed |
|---|---|---|---|---|---|---|
| CVPR 2025 | OpenAlex | 200 | 200 | 122 / 122 | 2025-06-01 to 06-10 | all on 2025-10-10 |
| CVPR 2026 | OpenAlex | - | - | over 150 | June 2026 | **not listed yet** (0 works dated after 2025-11-11) |
| ICCV 2025 | OpenAlex | 200 | 107 | 198 / 198 | 2025-10 | 2023-11 to 2026-05 (merged preprints) |
| NeurIPS 2025 | OpenAlex | 200 | 0 | - | all "2025-01-01" | 2024-10 to 2026-08 |
| AAAI 2026 | OpenAlex | 200 | 187 | 4 / 6 | 2026-03-14 | 2025-11 to 2026-03 |
| IJCAI 2025 | OpenAlex | 200 | 199 | 39 / 39 | 2025-09-01 | to 2025-10-10 |
| ACM MM 2025 | OpenAlex | 200 | 197 | 0 / 0 | 2025-10-25 | 2025-10-10 to 10-25 |
| ACM MM 2026 | OpenAlex | 846 | 841 | 1 / 1 | late Oct 2026 | in this window |
| ECCV 2026 | Crossref | about 2,800 | 0 (see below) | -1 / -1 | 2026-09-09 to 09-13 | 2026-09-08 to 10-04, median 09-12 |

ECCV 2026: Springer registered every chapter's DOI one day before the chapter's online date. The container-title search is fuzzy and returned 2,771 and 2,825 chapters in two runs, so the count is approximate; 106 of the 2,771 match Eric's topics on title alone (4 have abstracts in Crossref). ICML and ICLR are almost absent from OpenAlex (ICLR has 602 works in all years), as the 11-04 measurement found.

## Unreliable dates

- OpenAlex, window: 159 of 1,077 new works carry a 1 January placeholder (IEEE TVCG 53, TCSVT 59, TPAMI 28, TIP 19): IEEE early-access papers have only the year. 7 more (ACM MM 5, TOG 2) have a publication date after the listing date.
- Crossref, window: 219 of 345 new records have a year-only publication date (all four IEEE journals); 3 TCSVT records are dated after their registration. All ECCV chapters found (2,771 in the run checked) were registered a day before their publication date.
- Conference samples: NeurIPS 2025 200 of 200 dated 1 January; ICCV 2025 93 of 200 listed before their publication date (merged preprints); AAAI 13; ACM MM 3; IJCAI 1.
- For IEEE the true online date is not in either source. The note takes the Crossref registration date as the early-access date: IEEE registers the DOI when the early-access paper is posted, which is an assumption, not measured here.

## What a feed would bring

- **Journals**: about 25 new papers a day (Crossref, 345 in 14 days), of which about 1.1 a day match Eric's topics (15 by Crossref, 17 by OpenAlex, which has abstracts for IEEE). Well under the spec's "about 10 a day".
- **Conference bursts**: ACM MM added 81 topic matches in this window (one batch a year), ECCV 106 in September (every two years). A feed must cap or spread these, or they swamp one day.
- **Already on the site**: 26 of the 1,077 OpenAlex works (TPAMI 7, ACM MM 13, TOG 5, TVCG 1) were papers the site had shown from arXiv in the last 60 days, by arXiv ID or exact title; these should become "published in" marks, not new entries.
- **Abstracts**: OpenAlex has them for 94-100% of IEEE and ACM papers but only 11% of IJCV (Springer); Crossref has none for IEEE. Summaries for IJCV and Journal of Vision papers would mostly be title-only.

## OpenAlex quota

The key has 10,000 credits a day (a list request costs 1). This measurement used 240 OpenAlex requests over three runs (76 + 82 + 82) and 9,525 credits were left after the last; the extra conference and DOI checks added 6 requests to a run.

| Way to run the daily feed | OpenAlex requests a day |
|---|---|
| Re-scan every watch-list venue's works published since a year ago (needed because IEEE dates sit on 1 January) | 76 |
| The same for the journals only | 33 |
| Re-scan the last 30 / 90 days only (misses all IEEE early access) | 25 / 29 |
| Crossref (free, no quota) finds the day's ~25 new DOIs; OpenAlex fetches them in one `doi:` filter for abstract, OA link and arXiv version | 1-2 |

Any of these is under 1% of the daily budget. The last is cheapest and also catches journal versions that OpenAlex merged into older works.

## Verdicts

Rule (spec Q5): a median delay of 3 days or less is **daily**, slower is **weekly**; a source that lists nothing for a venue, or cannot be read, is **not worth it** for that venue.

Per source:

- **Crossref, journals: daily.** It is the first record of a journal paper: median 0 days (p90 0-1) for TOG, CGF, IJCV and Journal of Vision with exact dates; for IEEE it is the early-access date itself. 25 papers a day. No abstracts for IEEE, so use it to find DOIs, not to summarise.
- **OpenAlex, journals: daily.** Median 1 day behind the DOI (p90 1) for all eight journals with papers; abstracts for IEEE and ACM. Its own `created_date` misses merged journal versions, so feed it DOIs from Crossref or re-scan by publication date.
- **OpenAlex, conferences: weekly.** Proceedings arrive in yearly batches: CVPR 122 days, ICCV about 200, IJCAI 39, AAAI 4 (all slower than 3 days); ACM MM 0-1 days but once a year. NeurIPS: not worth it here (every date is 1 January). ICML and ICLR: not worth it here (hardly indexed).
- **Crossref, ECCV: daily** by the rule (registered 1 day before publication), but it is one batch of about 2,800 papers every two years.
- **OpenReview: not measured** (challenge required for anonymous scripts). ICLR, ICML, NeurIPS and TMLR need a logged-in rerun before a verdict.

Per venue group:

- **ML and CV conferences: weekly**, as batches on Sunday's page. Medians: CVPR 122, ICCV 198, IJCAI 39, AAAI 4, ACM MM 0, ECCV -1 days; arXiv already carries 62-85% of these papers (arxiv-coverage.md). NeurIPS, ICML, ICLR: no verdict until OpenReview is measured.
- **Graphics and VR (TOG, TVCG, CGF): daily.** Median 0 days in Crossref, 1 day in OpenAlex; 12.8 papers a day together (Crossref); 9 topic matches in 14 days (Crossref, TOG and TVCG).
- **Journals (TPAMI, IJCV, TIP, TCSVT): daily.** Same lags; 11.5 papers a day (Crossref); 10 topic matches in 14 days (OpenAlex). **JMLR and TMLR: not worth it** through OpenAlex or Crossref (0 papers: neither registers DOIs with Crossref, and OpenAlex lists 0 in the year); TMLR waits for OpenReview.
- **Vision science (Journal of Vision): daily**, but tiny: 5 papers in 14 days (n<20), median 0 days.

## What could not be measured, and why

- **OpenReview** (ICLR, ICML, NeurIPS, TMLR): the API answers anonymous scripts with a browser challenge. Not worked around; needs `OPENREVIEW_TOKEN` from Eric's account.
- **OpenAlex listing by created date**: `from_created_date` is a paid feature. The measurement re-scans publication dates instead, and so misses works published more than a year before they were listed.
- **True online dates of IEEE papers**: neither source has them (year only). The Crossref registration date stands in.
- **CVPR 2026 delay**: not listed in OpenAlex 5 months after the conference; the delay is "over 150 days", not a number. CVPR's IEEE DOIs were not checked in Crossref.
- **Seasonality**: one 14-day window. It held the ACM MM batch and no CVPR, ICCV or NeurIPS batch; papers a day for conferences depends on the month.
- **Small samples**: CGF (4-7), IJCV (9-17), TIP (19 in OpenAlex), Journal of Vision (3-5); JMLR, TMLR and most conferences had 0 in the window.
- **Renamed papers** and fuzzy titles: "already on the site" uses arXiv IDs and exact normalised titles, so it is a lower bound.
- **Open-access and arXiv shares in Crossref**: only licences and preprint relations that publishers deposit, so near 0 for IEEE and Springer.
