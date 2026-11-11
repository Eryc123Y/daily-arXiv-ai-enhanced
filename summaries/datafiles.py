"""The data branch's files: paths, reading records, publishing summaries, the run log, and command output."""

import json
import os
import re
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path

from summaries.databranch import DataBranch
from summaries.records import (
    dedupe_by_id,
    dump_jsonl,
    merge_summaries,
    parse_jsonl,
    pending_papers,
    without_abstract,
)

SITE_SETTINGS = "assets/site.json"
VENUES = "assets/venues.json"
WATCHLIST = Path(__file__).with_name("watchlist.json")
VENUE_KINDS = ("conference", "journal")
RUN_LOG = "logs/summary-runs.jsonl"
RAW_FILE = re.compile(r"^data/(\d{4}-\d{2}-\d{2})\.jsonl$")


def raw_path(day):
    return f"data/{day}.jsonl"


def ai_path(day, language):
    return f"data/{day}_AI_enhanced_{language}.jsonl"


def site_settings(language):
    """Published to the data branch so the page knows the crawled categories and the watched venues."""
    categories = [c.strip() for c in os.environ.get("CATEGORIES", "").split(",") if c.strip()]
    site = {SITE_SETTINGS: json.dumps({"categories": categories, "language": language}, indent=2) + "\n"} if categories else {}
    return {**site, **venue_settings()}


def venue_summary(path=WATCHLIST):
    """The watch list as the page needs it: [{name, kind, area}] in list order (VenueSummary in shapes.py).

    Entries without a name or a known kind are left out; a venue without an area gets area null.
    The feed checks the full list (feed.load_watchlist); this only reads it.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    venues = data.get("venues") if isinstance(data, dict) else None
    summary = []
    for venue in venues if isinstance(venues, list) else []:
        if not isinstance(venue, dict):
            continue
        name, kind, area = venue.get("name"), venue.get("kind"), venue.get("area")
        if isinstance(name, str) and name.strip() and kind in VENUE_KINDS:
            summary.append({"name": name.strip(), "kind": kind, "area": area.strip() if isinstance(area, str) and area.strip() else None})
    return summary


def venue_settings(path=WATCHLIST):
    """{assets/venues.json: text}, or {} when the watch list cannot be read (the page then shows no grouping)."""
    try:
        summary = venue_summary(path)
    except (OSError, ValueError):
        return {}
    return {VENUES: json.dumps(summary, ensure_ascii=False, indent=2) + "\n"}


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


def counts(raw, ai_records, abstracts=frozenset()):
    """total, done, pending; plus no_abstract (feed papers that cannot be summarised here) when there are any.

    `abstracts` holds the ids of feed papers whose abstract is in this machine's work folder.
    """
    total = len(dedupe_by_id(raw))
    pending = len(pending_papers(raw, ai_records, abstracts))
    missing = len(without_abstract(raw, ai_records, abstracts))
    stats = {"total": total, "done": total - pending - missing, "pending": pending}
    return {**stats, "no_abstract": missing} if missing else stats


def recent_days(branch, days):
    """Dates with a raw file in the last `days` days, newest first."""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    found = (m.group(1) for p in branch.list_files("data/") if (m := RAW_FILE.match(p)))
    return sorted((d for d in found if d >= cutoff), reverse=True)


def publish_summaries(branch, day, language, new, source, abstracts=frozenset()):
    stats = {}

    def build(current):
        raw = read_records(current, raw_path(day))
        merged = merge_summaries(raw, read_records(current, ai_path(day, language)), new)
        stats.clear()
        stats.update(counts(raw, merged, abstracts))
        return {ai_path(day, language): dump_jsonl(merged)}

    if new:
        branch.publish(build, f"summaries: {day} ({source})")
    else:
        branch.fetch()
        build(branch)
    return stats


def record_run(branch, day, language, path, reason=None, abstracts=frozenset()):
    """Append which summary path ran for `day` to logs/summary-runs.jsonl."""
    entry = {}

    def build(current):
        stats = counts(read_records(current, raw_path(day)), read_records(current, ai_path(day, language)), abstracts)
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
