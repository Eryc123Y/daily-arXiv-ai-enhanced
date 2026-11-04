# Competitive brief: where Daily arXiv sits (2026-11-03)

What this site is for: one researcher (Eric) reads a short Chinese report each morning that picks the few papers worth his time from about 450-1,300 new arXiv papers a day, flags papers that could collide with his project, and links into a page with an English summary of every paper. It runs on a Claude subscription and GitHub's free tier.

Sources: alphaXiv and Hugging Face Papers were checked on their live pages today. The rows for Scholar Inbox, arxiv-sanity-lite and Semantic Scholar feeds come from their public descriptions as I knew them and are marked "not checked today"; confirm before acting on them.

## The neighbours

| | What it does well | What it lacks for Eric |
|---|---|---|
| alphaXiv (checked) | Trending papers, discussion threads on each paper, following authors, chat over the full text (we already use its full-text queries for radar papers). | No reader-specific selection: trending is what everyone reads. No project-collision check. |
| Hugging Face Papers (checked) | Daily list curated by submitters, upvotes, linked models, datasets and Spaces, a daily email of trending papers. | Covers about 50 papers a day, mostly LLM and multimodal; little of stereo or weak-supervision theory. We already read its upvotes (`signals.yml`). |
| Scholar Inbox (not checked today) | Personal recommendations learned from the reader rating papers, a daily email digest. | The model behind the ranking is opaque to the reader; no summaries in the reader's language; no project brief. |
| arxiv-sanity-lite (not checked today) | Tags you assign, then a per-tag classifier over the abstracts recommends similar new papers; optional email. | No summaries; keeps working only if you keep tagging. |
| Semantic Scholar research feeds (not checked today) | Feeds trained from papers you add to a library, one-line TL;DRs, citation data. | English only, no project radar, no daily curated report. |

## Where we are different

1. **A project radar.** The writer grades each candidate against `project-brief.md` (high, medium, worth borrowing) and reads the full text when the grade depends on it. None of the neighbours knows what the reader is working on.
2. **A short report in the reader's language** with a reason for each pick, then one tap to the paper's English summary.
3. **The reader owns everything**: data on a public `data` branch, report and ledger in his Obsidian vault, prompts in this repository.
4. **Cost per day is known and small** (docs/daily-pipeline.md): roughly 1-10% of a 5-hour window on a Claude plan.

## What is worth learning from them

| Idea | From | How it would fit here | Roadmap |
|---|---|---|---|
| Learn from the reader's ratings, not only keywords | Scholar Inbox, arxiv-sanity, Semantic Scholar | A thumbs up or down on the page or a reply in the messenger chat; ratings feed the writer prompt now and embedding ranking later. Needs reading state (Next). | Next |
| Code, models and datasets beside the paper | Hugging Face Papers | Done for code (`code_url` from the listing, a Code mark and a Has code filter on the page, `[代码]` in the report); models and datasets would come from the HF API. | Now (done) / Later |
| Discussion around a paper | alphaXiv, HF | Show comment counts from alphaXiv and HF next to ▲; the report only mentions them when unusually high. | Later |
| A daily email | HF, Scholar Inbox | Not needed: the messenger routine and the push cover it. | Not planned |
| Follow authors | alphaXiv, Semantic Scholar | The site already matches followed authors; a weekly "new from people you follow" line in Sunday's page is cheap. | Next |

## Risks

- **Relying on one listing page.** arXiv was about ten hours late on 2026-11-03 and GitHub skipped scheduled runs; the 16:20 local run and the status line cover this.
- **Keyword topics miss papers phrased differently.** The writer can place any paper under any topic, but it only sees one line for papers without a keyword match. Embedding ranking (Next) is the fix.
- **Privacy.** The `data` branch is public, so radar reasons and the project brief stay in the vault.
