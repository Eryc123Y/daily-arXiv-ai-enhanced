"""Paper records: the raw crawl file and the summary file the site reads.

Invariant kept by every writer: each record in `<date>_AI_enhanced_<lang>.jsonl`
has an `AI` object with all five fields non-empty. Papers still waiting for a
summary live only in the raw `<date>.jsonl`; the site merges the two files.
"""

import json

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


def pending_papers(raw, ai_records):
    """Raw papers that do not yet have a complete summary, in raw order."""
    done = {r["id"] for r in ai_records if has_summary(r)}
    return [p for p in dedupe_by_id(raw) if p["id"] not in done]


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
