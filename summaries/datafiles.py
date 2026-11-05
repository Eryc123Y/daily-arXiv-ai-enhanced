"""The data branch's files: paths, reading records, publishing summaries, the run log, and command output."""

import json
import os
import re
import shlex
from datetime import datetime, timedelta, timezone

from summaries.databranch import DataBranch
from summaries.records import (
    dedupe_by_id,
    dump_jsonl,
    merge_summaries,
    parse_jsonl,
    pending_papers,
)

SITE_SETTINGS = "assets/site.json"
RUN_LOG = "logs/summary-runs.jsonl"
RAW_FILE = re.compile(r"^data/(\d{4}-\d{2}-\d{2})\.jsonl$")


def raw_path(day):
    return f"data/{day}.jsonl"


def ai_path(day, language):
    return f"data/{day}_AI_enhanced_{language}.jsonl"


def site_settings(language):
    """Published to the data branch so the page knows the crawled categories."""
    categories = [c.strip() for c in os.environ.get("CATEGORIES", "").split(",") if c.strip()]
    if not categories:
        return {}
    return {SITE_SETTINGS: json.dumps({"categories": categories, "language": language}, indent=2) + "\n"}


def emit(**values):
    """Print JSON for the caller and mirror scalars to $GITHUB_OUTPUT."""
    print(json.dumps(values, ensure_ascii=False, indent=2))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            for key, value in values.items():
                if isinstance(value, (str, int, bool)):
                    fh.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def make_branch(args):
    return DataBranch(args.repo, fetch_args=shlex.split(os.environ.get("DATA_FETCH_ARGS", "")))


def read_records(branch, path):
    return parse_jsonl(branch.read(path) or "")


def counts(raw, ai_records):
    total = len(dedupe_by_id(raw))
    pending = len(pending_papers(raw, ai_records))
    return {"total": total, "done": total - pending, "pending": pending}


def recent_days(branch, days):
    """Dates with a raw file in the last `days` days, newest first."""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    found = (m.group(1) for p in branch.list_files("data/") if (m := RAW_FILE.match(p)))
    return sorted((d for d in found if d >= cutoff), reverse=True)


def publish_summaries(branch, day, language, new, source):
    stats = {}

    def build(current):
        raw = read_records(current, raw_path(day))
        merged = merge_summaries(raw, read_records(current, ai_path(day, language)), new)
        stats.update(counts(raw, merged))
        return {ai_path(day, language): dump_jsonl(merged)}

    if new:
        branch.publish(build, f"summaries: {day} ({source})")
    else:
        branch.fetch()
        build(branch)
    return stats


def record_run(branch, day, language, path, reason=None):
    """Append which summary path ran for `day` to logs/summary-runs.jsonl."""
    entry = {}

    def build(current):
        stats = counts(read_records(current, raw_path(day)), read_records(current, ai_path(day, language)))
        entry.clear()
        entry.update(
            date=day,
            path=path,
            at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **stats,
            **({"reason": reason} if reason else {}),
        )
        return {RUN_LOG: (current.read(RUN_LOG) or "") + dump_jsonl([entry])}

    branch.publish(build, f"log: {day} {path}")
    return entry
