"""Paper records: the raw crawl file and the summary file the site reads.

Invariant kept by every writer: each record in `<date>_AI_enhanced_<lang>.jsonl`
has an `AI` object with all five fields non-empty. Papers still waiting for a
summary live only in the raw `<date>.jsonl`; the site merges the two files.
"""

import json
from collections.abc import Collection

AI_FIELDS = ("tldr", "motivation", "method", "result", "conclusion")


def clean_ai(value):
    """Return the five summary fields stripped, or None if any is unusable."""
    if not isinstance(value, dict):
        return None
    cleaned = {}
    for field in AI_FIELDS:
        text = value.get(field)
        if not isinstance(text, str) or not text.strip():
            return None
        cleaned[field] = text.strip()
    return cleaned


def is_arxiv(record):
    """A record without `source` is an arXiv record (every record written before the feed)."""
    return (record.get("source") or "arxiv") == "arxiv"


def has_summary(record):
    return isinstance(record, dict) and bool(record.get("id")) and clean_ai(record.get("AI")) is not None


def parse_jsonl(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def dump_jsonl(records):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def dedupe_by_id(records):
    seen = set()
    unique = []
    for record in records:
        if not isinstance(record, dict) or not record.get("id") or record["id"] in seen:
            continue
        seen.add(record["id"])
        unique.append(record)
    return unique


def unsummarised(raw, ai_records):
    done = {r["id"] for r in ai_records if has_summary(r)}
    return [p for p in dedupe_by_id(raw) if p["id"] not in done]


def pending_papers(raw, ai_records, abstracts: Collection[str] = frozenset()):
    """Raw papers that do not yet have a complete summary and can get one, in raw order.

    An arXiv record carries its abstract. A feed record can be summarised only
    while its abstract is in this machine's work folder (`abstracts`, ids or a
    dict); without it, it is never pending, so it cannot stay pending forever.
    """
    return [p for p in unsummarised(raw, ai_records) if is_arxiv(p) or p["id"] in abstracts]


def without_abstract(raw, ai_records, abstracts: Collection[str] = frozenset()):
    """Feed records with no summary and no local abstract: listed, never summarised."""
    return [p for p in unsummarised(raw, ai_records) if not is_arxiv(p) and p["id"] not in abstracts]


def with_abstracts(papers, abstracts):
    """Copies of `papers` with each feed record's local abstract as `summary`, for the summary prompt only."""
    return [p if is_arxiv(p) else {**p, "summary": abstracts.get(p["id"], "")} for p in papers]


def merge_summaries(raw, existing_ai_records, new_summaries):
    """Build the summary file: raw order, complete records only.

    Existing summaries win over new ones so a re-run never rewrites what is
    already published. Summaries for ids that are not in `raw` are dropped.
    """
    existing = {r["id"]: r for r in existing_ai_records if has_summary(r)}
    merged = []
    for paper in dedupe_by_id(raw):
        if paper["id"] in existing:
            merged.append(existing[paper["id"]])
            continue
        ai = clean_ai(new_summaries.get(paper["id"]))
        if ai is not None:
            merged.append({**paper, "AI": ai})
    return merged
