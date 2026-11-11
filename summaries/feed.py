"""Papers from journals and conferences, read from a feed command and published beside arXiv's.

The feed's source adapters live in LitScout (spec S1, Q1); this pipeline only
runs its command. FEED_COMMAND is a JSON argv list; the pipeline appends
`--since YYYY-MM-DD --venues <watch list>` and reads JSON Lines from stdout,
one paper per line (shape `FeedLine` in shapes.py). `--since` asks for papers
the sources listed on or after that day.

Feed papers are published under the day they were fetched, in the same raw
file as that day's arXiv papers, so a two-week-old journal paper reaches
today's page instead of an old day nobody opens. The cursor
(`assets/feed-cursor.json`) moves in the same commit as the papers (R1):
a run after missed days publishes them once, and the next run nothing.
Abstracts stay in the local work folder (abstracts.py).
"""

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from summaries import abstracts, dedupe
from summaries.datafiles import RAW_FILE, raw_path, read_records
from summaries.records import dedupe_by_id, dump_jsonl

SOURCES = ("openalex", "crossref", "openreview")  # R6: official APIs only; nothing else is accepted
WATCHLIST = Path(__file__).with_name("watchlist.json")
FEED_CURSOR = "assets/feed-cursor.json"
FIRST_LOOKBACK_DAYS = 7  # how far back the very first run asks
HISTORY_DAYS = 60  # dedupe looks this far back on the data branch
MAX_PER_RUN = 150  # FEED_MAX_PER_RUN default: proceedings arrive in one batch (ECCV about 2,800, Phase 0)
FEED_TIMEOUT = 30 * 60
KINDS = ("conference", "journal")
VENUE_FIELDS = {"name", "kind", "group", "issn", "openalex_source", "openreview_venues", "sources"}
LIST_FIELDS = ("issn", "openreview_venues")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WEB = re.compile(r"^https?://\S+$")


class FeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeedPaper:
    record: dict  # FeedRecord, as published
    abstract: str | None  # kept locally only


# --- Watch list ---------------------------------------------------------------


def _check_venue(venue):
    if not isinstance(venue, dict):
        raise FeedError(f"watch list: {venue!r} is not an object")
    name = venue.get("name")
    if not isinstance(name, str) or not name.strip():
        raise FeedError(f"watch list: a venue has no name ({venue!r})")
    if venue.get("kind") not in KINDS:
        raise FeedError(f"watch list: {name} has kind {venue.get('kind')!r}; use {' or '.join(KINDS)}")
    if not isinstance(venue.get("group"), str):
        raise FeedError(f"watch list: {name} has no group")
    unknown = set(venue) - VENUE_FIELDS
    if unknown:
        raise FeedError(f"watch list: {name} has unknown fields {sorted(unknown)}")
    for key in LIST_FIELDS:
        value = venue.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise FeedError(f"watch list: {name} {key} must be a list of strings")
    if "openalex_source" in venue and not _text(venue["openalex_source"]):
        raise FeedError(f"watch list: {name} openalex_source must be a string")
    sources = venue.get("sources", list(SOURCES))
    outside = [s for s in sources if s not in SOURCES] if isinstance(sources, list) else [sources]
    if outside:
        raise FeedError(f"watch list: {name} names sources {outside}; only {', '.join(SOURCES)} are allowed")


def load_watchlist(path=WATCHLIST):
    """The venues of the watch list file, checked; FeedError if any entry is wrong."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise FeedError(f"watch list {path} cannot be read: {error}") from error
    venues = data.get("venues") if isinstance(data, dict) else None
    if not isinstance(venues, list) or not venues:
        raise FeedError(f"watch list {path} has no venues")
    for venue in venues:
        _check_venue(venue)
    return venues


# --- Lines --------------------------------------------------------------------


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional(value):
    """A string field that may be null: (ok, cleaned)."""
    return (value is None or isinstance(value, str)), _text(value)


def _paper_id(arxiv_id, doi, openreview_id):
    if arxiv_id:
        return arxiv_id
    if doi:
        return f"doi:{doi}"
    return f"openreview:{openreview_id}" if openreview_id else None


def _valid_day(value):
    if not isinstance(value, str) or not DAY.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def parse_line(text):
    """A FeedPaper from one output line, or None if the line breaks the contract."""
    try:
        line = json.loads(text)
    except ValueError:
        return None
    if not isinstance(line, dict) or line.get("source") not in SOURCES:
        return None
    title, venue, url = _text(line.get("title")), _text(line.get("venue")), _text(line.get("url"))
    authors = line.get("authors")
    optional = {k: _optional(line.get(k)) for k in ("doi", "arxiv_id", "openreview_id", "abstract", "oa_url")}
    if not (title and venue and url and WEB.match(url) and _valid_day(line.get("published"))):
        return None
    if not isinstance(authors, list) or not all(isinstance(a, str) for a in authors):
        return None
    if not all(ok for ok, _ in optional.values()):
        return None
    oa_url = optional["oa_url"][1]
    if oa_url and not WEB.match(oa_url):
        return None
    doi = dedupe.normalise_doi(optional["doi"][1])
    paper_id = _paper_id(dedupe.normalise_arxiv_id(optional["arxiv_id"][1]), doi, optional["openreview_id"][1])
    if not paper_id:
        return None
    record = {
        "id": paper_id,
        "source": line["source"],
        "title": " ".join(title.split()),
        "authors": [a.strip() for a in authors if a.strip()],
        "venue": venue,
        "published": line["published"],
        "doi": doi,
        "oa_url": oa_url,
        "url": url,
        "categories": [],
        "has_abstract": bool(optional["abstract"][1]),
    }
    return FeedPaper(record=record, abstract=optional["abstract"][1])


def parse_output(text):
    """(papers, number of invalid lines) from the command's stdout; blank lines are ignored."""
    papers, invalid = [], 0
    for text_line in text.splitlines():
        if not text_line.strip():
            continue
        paper = parse_line(text_line)
        if paper is None:
            invalid += 1
        else:
            papers.append(paper)
    return papers, invalid


# --- The command ---------------------------------------------------------------


def feed_command(env):
    """FEED_COMMAND as an argv list, or None when it is unset; FeedError when it is not a JSON list of strings."""
    raw = (env.get("FEED_COMMAND") or "").strip()
    if not raw:
        return None
    try:
        argv = json.loads(raw)
    except ValueError as error:
        raise FeedError("FEED_COMMAND must be a JSON list, e.g. [\"litscout\", \"watch\"]") from error
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        raise FeedError("FEED_COMMAND must be a non-empty JSON list of strings")
    return argv


def run_command(argv, since, venues, cwd):
    """The command's stdout; FeedError with its one-line reason when it fails."""
    full = [*argv, "--since", since, "--venues", str(venues)]
    try:
        result = subprocess.run(full, cwd=str(cwd), capture_output=True, text=True, timeout=FEED_TIMEOUT, stdin=subprocess.DEVNULL, check=False)
    except (subprocess.TimeoutExpired, OSError) as error:
        raise FeedError(f"the feed command did not finish: {error}") from error
    if result.returncode != 0:
        reason = (result.stderr or "").strip().splitlines()[-1:] or [f"exit code {result.returncode}"]
        raise FeedError(f"the feed command failed: {reason[0][:200]}")
    return result.stdout


# --- Cursor and publishing -------------------------------------------------------


def cursor_since(branch, day):
    """The day the next request starts from: the stored cursor, else FIRST_LOOKBACK_DAYS before `day`."""
    try:
        stored = json.loads(branch.read(FEED_CURSOR) or "null")
    except ValueError:
        stored = None
    since = stored.get("since") if isinstance(stored, dict) else None
    if _valid_day(since):
        return since
    return (date.fromisoformat(day) - timedelta(days=FIRST_LOOKBACK_DAYS)).isoformat()


def history(branch, day, days=HISTORY_DAYS):
    """Every record in the raw files of the `days` days up to and including `day`."""
    start = (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    records = []
    for path in branch.list_files("data/"):
        match = RAW_FILE.match(path)
        if match and start <= match.group(1) <= day:
            records += read_records(branch, path)
    return records


def max_per_run(env):
    """FEED_MAX_PER_RUN, a positive integer, else MAX_PER_RUN."""
    try:
        value = int(env.get("FEED_MAX_PER_RUN") or MAX_PER_RUN)
    except ValueError:
        return MAX_PER_RUN
    return value if value > 0 else MAX_PER_RUN


def publish(branch, day, papers, work_dir, limit=MAX_PER_RUN):
    """Publish the papers not already on the branch under `day`, moving the cursor in the same commit.

    At most `limit` new papers go in, first come first; when more arrived the cursor stays, so the next
    run asks for the same window again and dedupe drops what this one published (`deferred` in the report).
    """
    result = {}
    at = datetime.now(UTC).isoformat(timespec="seconds")

    def build(current):
        fresh, dropped = dedupe.fresh(history(current, day), papers)
        kept = fresh[:limit]
        existing = read_records(current, raw_path(day))
        combined = dedupe_by_id(existing + [p.record for p in kept])
        result.update(kept=kept, duplicates=dropped, deferred=len(fresh) - len(kept), added=len(combined) - len(existing))
        moves = not result["deferred"] and not (cursor_since(current, day) == day and current.read(FEED_CURSOR))
        cursor = {FEED_CURSOR: json.dumps({"since": day, "at": at}, indent=2) + "\n"} if moves else {}
        return {raw_path(day): dump_jsonl(combined), **cursor} if result["added"] else cursor

    # Abstracts are saved before the push: one saved for a paper a racing run published instead is harmless,
    # while a paper published without its local abstract would get no summary.
    build(branch)
    abstracts.save(work_dir, {p.record["id"]: p.abstract for p in result["kept"] if p.abstract})
    commit = branch.publish(build, f"update: {day} feed papers")
    return {
        "added": result["added"],
        "duplicates": result["duplicates"],
        "deferred": result["deferred"],
        "no_abstract": sum(1 for p in result["kept"] if not p.abstract),
        "commit": commit or "",
    }


def run(branch, day, repo_dir, work_dir, env):
    """The `feed` part of ensure-day's report: "skipped" without FEED_COMMAND, else what was published."""
    try:
        argv = feed_command(env)
        if argv is None:
            return "skipped"
        load_watchlist(WATCHLIST)
    except FeedError as error:
        return {"status": "error", "reason": str(error)}
    branch.fetch()
    since = cursor_since(branch, day)
    try:
        output = run_command(argv, since, WATCHLIST, repo_dir)
    except FeedError as error:
        return {"status": "error", "since": since, "reason": str(error)}
    papers, invalid = parse_output(output)
    published = publish(branch, day, papers, work_dir, max_per_run(env))
    status = "published" if published["added"] else "nothing new"
    return {"status": status, "since": since, "received": len(papers), "invalid": invalid, **published}
