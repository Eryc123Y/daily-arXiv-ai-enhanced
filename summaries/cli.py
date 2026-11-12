"""Command line for the daily pipeline.

Crawl:        ensure-day (crawl arXiv on this machine, backfill missed days),
              ingest (publish a crawl file), hf-signals (Hugging Face upvotes)
Summaries:    run-local (headless coding agent), api (LLM API), mode,
              status, prepare, merge, finish (subagent summaries),
              handover (usage gate reached: API here or pause), record (run log)
Reports:      digest (the short Chinese report), digest-week, missed
"""

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from summaries import (
    abstract_retry,
    abstracts,
    digest,
    feed,
    github,
    local_runner,
    localcrawl,
    missed,
    setup,
    signals,
    weekly,
)
from summaries.databranch import PublishError
from summaries.datafiles import (
    RAW_FILE,
    RUN_LOG,
    ai_path,
    counts,
    emit,
    make_branch,
    publish_summaries,
    raw_path,
    read_records,
    recent_days,
    record_run,
    site_settings,
    venue_day_counts,
    venue_days_file,
    venue_settings,
    with_venue_days,
)
from summaries.localtask import acquire_lock, merge_outputs, release_lock, write_chunks
from summaries.mode import resolve_mode
from summaries.providers import resolve_provider
from summaries.records import (
    dedupe_by_id,
    dump_jsonl,
    is_arxiv,
    parse_jsonl,
    pending_papers,
    with_abstracts,
)

INGEST_HISTORY_DAYS = 7
HANDOVER_BATCH = 50
HANDOVER_WORKERS = 8
# --- Actions -----------------------------------------------------------------


def history_ids(branch, day, days):
    start = day - timedelta(days=days)
    ids = set()
    for path in branch.list_files("data/"):
        match = RAW_FILE.match(path)
        if match and start <= date.fromisoformat(match.group(1)) < day:
            ids.update(r["id"] for r in read_records(branch, path))
    return ids


def publish_crawl(branch, day, crawled, history_days, language, dry_run=None):
    """Publish crawled rows as the day's raw file, minus papers seen in the last `history_days`.

    Returns what `ingest` reports. `dry_run` is a path to write the day's file to instead of pushing.
    """
    crawled = dedupe_by_id(crawled)
    branch.fetch()
    seen = history_ids(branch, date.fromisoformat(day), history_days)
    fresh = [p for p in crawled if p["id"] not in seen]
    result = {}
    at = datetime.now(UTC).isoformat(timespec="seconds")

    def build(current):
        existing = read_records(current, raw_path(day))
        combined = dedupe_by_id(existing + fresh)
        result.update(added=len(combined) - len(existing), papers=len(combined))
        # When the papers landed, for the week's health table and the status line.
        entry = {"date": day, "path": "crawl", "at": at, "total": len(combined), "added": result["added"]}
        log = (current.read(RUN_LOG) or "") + dump_jsonl([entry])
        return with_venue_days(current, {raw_path(day): dump_jsonl(combined), RUN_LOG: log, **site_settings(language)})

    content = build(branch)
    report = {"crawled": len(crawled), "already_seen": len(crawled) - len(fresh)}
    if result["added"] == 0:
        return {"has_new_content": False, **report, "added": 0}
    commit = None if dry_run else branch.publish(build, f"update: {day} arXiv papers")
    if dry_run:
        Path(dry_run).write_text(content[raw_path(day)], encoding="utf-8")
    return {"has_new_content": True, **report, "added": result["added"], "papers": result["papers"], "commit": commit or ""}


def cmd_ingest(args):
    """Publish the crawl as the day's raw file, minus papers seen in the last week."""
    crawled = parse_jsonl(Path(args.input).read_text(encoding="utf-8"))
    emit(**publish_crawl(make_branch(args), args.date, crawled, args.history_days, args.language, args.dry_run))
    return 0


def cmd_mode(args):
    _, problem = resolve_provider(os.environ)
    decision = resolve_mode(os.environ.get("SUMMARY_MODE", ""), problem)
    if decision.warning:
        print(f"::warning::{decision.warning}")
    emit(mode=decision.mode)
    return 0


def api_summaries(branch, days, language, batch_size, max_workers, config, local=None):
    """Summarise the days' pending papers through the API; returns (requested, summarised, failures).

    `local` is {id: abstract} of feed papers from this machine's work folder (empty in Actions).
    """
    local = local or {}
    from summaries import providers
    from summaries.llm import summarize_all

    call = None
    requested = summarised = 0
    failures = []
    for day in days:
        raw = read_records(branch, raw_path(day))
        todo = with_abstracts(pending_papers(raw, read_records(branch, ai_path(day, language)), local), local)
        if not todo:
            continue
        call = call or providers.make_summarizer(config, os.environ)
        for start in range(0, len(todo), batch_size):
            batch = todo[start : start + batch_size]
            outcomes = summarize_all(call, batch, language, max_workers=max_workers)
            new = {o.paper_id: o.ai for o in outcomes if o.ai}
            publish_summaries(branch, day, language, new, "api", local)
            requested += len(batch)
            summarised += len(new)
            failures += [(day, o) for o in outcomes if o.ai is None]
    return requested, summarised, failures


def cmd_api(args):
    config, problem = resolve_provider(os.environ)
    if config is None or problem:
        print(f"::error::Cannot summarise with the API: {problem}.")
        return 2
    print(f"Summarising with {config.provider} ({config.model})")
    branch = make_branch(args)
    branch.fetch()
    days = [args.date] if args.date else recent_days(branch, args.days)
    local = abstracts.load(args.work_dir)
    requested, summarised, failures = api_summaries(branch, days, args.language, args.batch_size, args.max_workers, config, local)
    for day, failure in failures[:20]:
        print(f"::warning::{failure.paper_id} left pending: {failure.error}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"API summaries: {summarised} written, {len(failures)} left pending.\n")
            fh.writelines(f"- {day} {f.paper_id}: {f.error}\n" for day, f in failures)
    emit(requested=requested, summarised=summarised, failed=len(failures))
    return 1 if requested and not summarised else 0


# --- Run log and API fallback ------------------------------------------------


def cmd_record(args):
    branch = make_branch(args)
    emit(**record_run(branch, args.date, args.language, args.path, args.reason, abstracts.load(args.work_dir)))
    return 0


def cmd_handover(args):
    """Usage gate reached: finish the day through the API here when a key is configured, or pause.

    The key is read from this machine's environment only by the provider
    client; it is never printed or stored. A paused day resumes on the next
    scheduled run once usage allows.
    """
    merged = merge_outputs(args)
    problem = None
    if merged["pending"] == 0:
        path = "claude-code"
    else:
        config, problem = resolve_provider(os.environ)
        if problem is None:
            branch = make_branch(args)
            branch.fetch()
            api_summaries(branch, [args.date], args.language, HANDOVER_BATCH, HANDOVER_WORKERS, config, abstracts.load(args.work_dir))
            path = "api-fallback"
        else:
            path = "paused-no-key"
    reason = "; ".join(filter(None, [args.reason, problem])) or None
    entry = record_run(make_branch(args), args.date, args.language, path, reason, abstracts.load(args.work_dir))
    emit(**entry, problems=merged["problems"])
    return 0


def published_days(branch):
    return sorted(m.group(1) for path in branch.list_files("data/") if (m := RAW_FILE.match(path)))


def arxiv_records(branch, day):
    """The day's arXiv papers; a day holding only feed papers has none."""
    return [r for r in read_records(branch, raw_path(day)) if is_arxiv(r)]


def last_arxiv_day(branch, before):
    """The newest day before `before` with arXiv papers, reading files newest first (usually one)."""
    for day in reversed([d for d in published_days(branch) if d < before]):
        if arxiv_records(branch, day):
            return day
    return None


def weekdays_between(start, end):
    """Weekdays strictly between two ISO days."""
    current, last = date.fromisoformat(start) + timedelta(days=1), date.fromisoformat(end)
    days = []
    while current < last:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def utc_today():
    return datetime.now(UTC).date().isoformat()


def backfill(args, branch, slug, missing):
    """Publish missed weekdays from the /recent listing.

    Days older than the listing's five announcements cannot be recovered and
    are reported as `gap`; a weekday inside its range that it does not show
    had no announcement (a holiday) and is neither.
    """
    try:
        listing = localcrawl.recent(args.repo, slug, missing)
    except localcrawl.CrawlError as error:
        return {"backfilled": {}, "gap": missing, "backfill_error": str(error)}
    backfilled = {}
    for day in missing:
        if day in listing.days:
            backfilled[day] = publish_crawl(branch, day, listing.days[day], INGEST_HISTORY_DAYS, args.language)["added"]
    oldest = listing.covered[0] if listing.covered else None
    gap = [d for d in missing if d not in listing.days and (oldest is None or d < oldest)]
    return {"backfilled": backfilled, "gap": gap}


def ensure_arxiv(args, branch, day, today):
    """(exit code, report) of the arXiv part of ensure-day. Feed papers on a day do not count as its arXiv crawl."""
    slug = github.repo_slug(args.repo)
    weekday = date.fromisoformat(day).weekday() < 5
    earlier = last_arxiv_day(branch, day)
    missing = weekdays_between(earlier, day) if earlier else []
    if weekday and day != today and not arxiv_records(branch, day):
        missing.append(day)
    report = backfill(args, branch, slug, missing) if missing else {}
    if not weekday:
        return 0, {"date": day, "status": "weekend", **report}
    branch.fetch()
    if arxiv_records(branch, day) or day != today:
        total = len(dedupe_by_id(read_records(branch, raw_path(day))))
        return 0, {"date": day, "status": "present" if total else "missing", "total": total, **report}
    try:
        crawled = localcrawl.crawl(args.repo, slug)
    except localcrawl.CrawlError as error:
        return 1, {"date": day, "status": "error", "reason": str(error), **report}
    result = publish_crawl(branch, day, crawled, INGEST_HISTORY_DAYS, args.language)
    branch.fetch()
    total = len(dedupe_by_id(read_records(branch, raw_path(day))))
    return 0, {"date": day, "status": "present" if total else "missing", "added": result["added"], "total": total, **report}


def cmd_ensure_day(args):
    """Make sure a weekday's papers are published: crawl today's on this machine, backfill missed days,
    then publish the feed's papers under today (any day of the week; skipped without FEED_COMMAND),
    fill missing feed abstracts (off without ABSTRACTS_COMMAND), and keep the public venue list current."""
    today = utc_today()
    day = args.date or today
    branch = make_branch(args)
    branch.fetch()
    code, report = ensure_arxiv(args, branch, day, today)
    if day == today:
        report["feed"] = feed.run(branch, day, args.repo, args.work_dir, os.environ)
        report["abstracts"] = abstract_retry.run(branch, day, args.repo, args.work_dir, os.environ)
    report.update(publish_venues(branch))
    emit(**report)
    return code


def publish_venues(branch):
    """Bring assets/venues.json and assets/venue-days.json up to date when no crawl or feed commit did.

    The venue-day counts are recounted from every raw file, so a missing or stale file is repaired once
    per run. {} when both already were.
    """
    def build(current):
        return {**venue_settings(), **venue_days_file(venue_day_counts(current))}

    try:
        commit = branch.publish(build, "update: venue list")
    except PublishError as error:
        return {"venues": {"status": "error", "reason": str(error)}}
    return {"venues": "published"} if commit else {}


# --- Claude Code local task ---------------------------------------------------


def cmd_status(args):
    branch = make_branch(args)
    branch.fetch()
    report = []
    local = abstracts.load(args.work_dir)
    for day in recent_days(branch, args.days):
        stats = counts(read_records(branch, raw_path(day)), read_records(branch, ai_path(day, args.language)), local)
        report.append({"date": day, **stats})
    print(json.dumps({"dates": report}, ensure_ascii=False, indent=2))
    return 0


def cmd_merge(args):
    emit(**merge_outputs(args))
    return 0


def cmd_prepare(args):
    root = Path(args.work_dir)
    holder = acquire_lock(root, args.force)
    if holder:
        emit(locked=True, holder=holder)
        return 3
    try:
        plan = write_chunks(args)
    except BaseException:
        release_lock(root)
        raise
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def cmd_finish(args):
    release_lock(Path(args.work_dir))
    for directory in Path(args.work_dir).glob("*/merged"):
        if directory.parent.name < (date.today() - timedelta(days=14)).isoformat():
            shutil.rmtree(directory.parent)
    print("lock released")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m summaries")
    parser.add_argument("--repo", default=".", help="git checkout whose remote holds the data branch")
    parser.add_argument("--language", default=os.environ.get("LANGUAGE") or "English")
    parser.add_argument("--work-dir", default=".cache/summaries")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="publish the crawl as data/<date>.jsonl")
    ingest.add_argument("--date", required=True)
    ingest.add_argument("--input", required=True)
    ingest.add_argument("--history-days", type=int, default=INGEST_HISTORY_DAYS)
    ingest.add_argument("--dry-run", metavar="PATH", help="write the day's file here instead of pushing")
    ingest.set_defaults(func=cmd_ingest)

    sub.add_parser("mode", help="resolve SUMMARY_MODE").set_defaults(func=cmd_mode)

    api = sub.add_parser("api", help="summarise pending papers with the Anthropic API")
    api.add_argument("--date", help="one day; default: every recent day with pending papers")
    api.add_argument("--days", type=int, default=3)
    api.add_argument("--max-workers", type=int, default=8)
    api.add_argument("--batch-size", type=int, default=50, help="papers per published commit")
    api.set_defaults(func=cmd_api)

    status = sub.add_parser("status", help="summary progress for recent days")
    status.add_argument("--days", type=int, default=7)
    status.set_defaults(func=cmd_status)

    prepare = sub.add_parser("prepare", help="write chunk files for pending papers")
    prepare.add_argument("--date", required=True)
    prepare.add_argument("--chunk-size", type=int, default=20)
    prepare.add_argument("--force", action="store_true", help="take over the lock (this run's own, or a stuck one)")
    prepare.set_defaults(func=cmd_prepare)

    merge = sub.add_parser("merge", help="publish subagent outputs to the data branch")
    merge.add_argument("--date", required=True)
    merge.set_defaults(func=cmd_merge)

    sub.add_parser("finish", help="release the lock").set_defaults(func=cmd_finish)

    local_runner.add_parser(sub)
    setup.add_parser(sub)
    digest.add_parser(sub)
    weekly.add_parser(sub)
    missed.add_parser(sub)
    signals.add_parser(sub)

    handover = sub.add_parser("handover", help="usage gate reached: start the API job or pause")
    handover.add_argument("--date", required=True)
    handover.add_argument("--reason", help="why, e.g. 'weekly 81%%'")
    handover.set_defaults(func=cmd_handover)

    ensure = sub.add_parser("ensure-day", help="crawl today's papers here and backfill missed days")
    ensure.add_argument("--date", help="UTC day, default today")
    ensure.set_defaults(func=cmd_ensure_day)

    record = sub.add_parser("record", help="log which summary path ran for a day")
    record.add_argument("--date", required=True)
    record.add_argument("--path", required=True, help="claude-code, api, api-fallback, paused-usage, ...")
    record.add_argument("--reason")
    record.set_defaults(func=cmd_record)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
