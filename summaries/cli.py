"""Command line for the daily pipeline.

Actions:      ingest (crawl -> data branch), mode, api (API-mode summaries)
Local task:   ensure-day (start a skipped crawl), run-local (summaries through
              a headless coding agent), digest (the short Chinese report),
              status, prepare, merge, finish (subagent summaries),
              handover (usage gate reached: API job or pause), record (run log)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from summaries import digest, github, local_runner, missed, setup, signals, weekly
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
)
from summaries.localtask import acquire_lock, merge_outputs, release_lock, write_chunks
from summaries.mode import resolve_mode
from summaries.providers import KEY_ENV, resolve_provider
from summaries.records import dedupe_by_id, dump_jsonl, parse_jsonl, pending_papers

API_WORKFLOW = "summarize-api.yml"
CRAWL_WORKFLOW = "run.yml"
ACTIVE_RUN = {"queued", "in_progress", "waiting", "pending", "requested"}
POLL_SECONDS = 20
# --- Actions -----------------------------------------------------------------


def history_ids(branch, day, days):
    start = day - timedelta(days=days)
    ids = set()
    for path in branch.list_files("data/"):
        match = RAW_FILE.match(path)
        if match and start <= date.fromisoformat(match.group(1)) < day:
            ids.update(r["id"] for r in read_records(branch, path))
    return ids


def cmd_ingest(args):
    """Publish the crawl as the day's raw file, minus papers seen in the last week."""
    day = date.fromisoformat(args.date)
    crawled = dedupe_by_id(parse_jsonl(Path(args.input).read_text(encoding="utf-8")))
    branch = make_branch(args)
    branch.fetch()
    seen = history_ids(branch, day, args.history_days)
    fresh = [p for p in crawled if p["id"] not in seen]
    result = {}
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def build(current):
        existing = read_records(current, raw_path(args.date))
        combined = dedupe_by_id(existing + fresh)
        result.update(added=len(combined) - len(existing), papers=len(combined))
        # When the papers landed, for the week's health table and the status line.
        entry = {"date": args.date, "path": "crawl", "at": at, "total": len(combined), "added": result["added"]}
        log = (current.read(RUN_LOG) or "") + dump_jsonl([entry])
        return {raw_path(args.date): dump_jsonl(combined), RUN_LOG: log, **site_settings(args.language)}

    content = build(branch)
    if result["added"] == 0:
        emit(has_new_content=False, crawled=len(crawled), already_seen=len(crawled) - len(fresh), added=0)
        return 0
    commit = None if args.dry_run else branch.publish(build, f"update: {args.date} arXiv papers")
    if args.dry_run:
        Path(args.dry_run).write_text(content[raw_path(args.date)], encoding="utf-8")
    emit(
        has_new_content=True,
        crawled=len(crawled),
        already_seen=len(crawled) - len(fresh),
        added=result["added"],
        papers=result["papers"],
        commit=commit or "",
    )
    return 0


def cmd_mode(args):
    _, problem = resolve_provider(os.environ)
    decision = resolve_mode(os.environ.get("SUMMARY_MODE", ""), problem)
    if decision.warning:
        print(f"::warning::{decision.warning}")
    emit(mode=decision.mode)
    return 0


def cmd_api(args):
    from summaries import providers
    from summaries.llm import summarize_all

    config, problem = resolve_provider(os.environ)
    if problem:
        print(f"::error::Cannot summarise with the API: {problem}.")
        return 2
    print(f"Summarising with {config.provider} ({config.model})")
    branch = make_branch(args)
    branch.fetch()
    call = None
    requested = summarised = 0
    failures = []
    for day in [args.date] if args.date else recent_days(branch, args.days):
        raw = read_records(branch, raw_path(day))
        todo = pending_papers(raw, read_records(branch, ai_path(day, args.language)))
        if not todo:
            continue
        call = call or providers.make_summarizer(config, os.environ)
        for start in range(0, len(todo), args.batch_size):
            batch = todo[start : start + args.batch_size]
            outcomes = summarize_all(call, batch, args.language, max_workers=args.max_workers)
            new = {o.paper_id: o.ai for o in outcomes if o.ai}
            publish_summaries(branch, day, args.language, new, "api")
            requested += len(batch)
            summarised += len(new)
            failures += [(day, o) for o in outcomes if o.ai is None]
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
    emit(**record_run(branch, args.date, args.language, args.path, args.reason))
    return 0


class SettingsUnavailable(RuntimeError):
    pass


def gh_variable(slug, name):
    """A repository variable's value, "" when it is not set."""
    try:
        return github.gh("variable", "get", name, "-R", slug).strip()
    except subprocess.CalledProcessError as error:
        if "not found" in (error.stderr or ""):
            return ""
        raise SettingsUnavailable(f"could not read {name}: {(error.stderr or str(error)).strip()}") from error


def remote_api_problem(slug):
    """What keeps the repository's API job from running, or None.

    Reads the SUMMARY_PROVIDER and SUMMARY_MODEL variables and only the
    names of the secrets; no key value is ever read.
    """
    try:
        secrets = {s["name"] for s in json.loads(github.gh("secret", "list", "-R", slug, "--json", "name") or "[]")}
        env = {name: gh_variable(slug, name) for name in ("SUMMARY_PROVIDER", "SUMMARY_MODEL")}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return f"could not read the repository secrets: {(getattr(error, 'stderr', None) or str(error)).strip()}"
    except SettingsUnavailable as error:
        return str(error)
    env.update({name: "set" for name in KEY_ENV.values() if name in secrets})
    return resolve_provider(env)[1]


def api_key_configured(slug):
    return remote_api_problem(slug) is None


def cmd_handover(args):
    """Usage gate reached: hand the day's remainder to the Actions API job, or pause.

    Only the secrets' names are checked; key values never leave GitHub.
    """
    merged = merge_outputs(args)
    problem = None
    if merged["pending"] == 0:
        path = "claude-code"
    else:
        slug = github.repo_slug(args.repo)
        problem = remote_api_problem(slug)
        if problem is None:
            github.gh("workflow", "run", API_WORKFLOW, "-R", slug, "-f", f"date={args.date}")
            path = "api-fallback"
        else:
            path = "paused-no-key"
    reason = "; ".join(filter(None, [args.reason, problem])) or None
    entry = record_run(make_branch(args), args.date, args.language, path, reason)
    emit(**entry, problems=merged["problems"])
    return 0


def crawl_runs(slug):
    fields = "databaseId,status,conclusion"
    return json.loads(github.gh("run", "list", "--workflow", CRAWL_WORKFLOW, "-R", slug, "-L", "5", "--json", fields) or "[]")


def wait_for_crawl(slug, seen, watch, wait):
    """Poll until the watched runs have finished: the ones in `watch`, or else the first new run.

    Returns their conclusions, or None if the wait ran out. A failed listing is retried.
    """
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        try:
            runs = crawl_runs(slug)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        mine = [r for r in runs if r["databaseId"] in watch] if watch else [r for r in runs if r["databaseId"] not in seen]
        if mine and not any(r["status"] in ACTIVE_RUN for r in mine):
            return [r.get("conclusion") or "" for r in mine]
    return None


def cmd_ensure_day(args):
    """Make sure a weekday's crawl ran: start it from here when GitHub's schedule skipped it."""
    day = args.date or datetime.now(timezone.utc).date().isoformat()
    if date.fromisoformat(day).weekday() >= 5:
        emit(date=day, status="weekend")
        return 0
    branch = make_branch(args)
    branch.fetch()
    raw = read_records(branch, raw_path(day))
    if raw:
        emit(date=day, status="present", dispatched=False, total=len(dedupe_by_id(raw)))
        return 0
    slug = github.repo_slug(args.repo)
    try:
        runs = crawl_runs(slug)
        running = {r["databaseId"] for r in runs if r["status"] in ACTIVE_RUN}
        if not running:
            github.gh("workflow", "run", CRAWL_WORKFLOW, "-R", slug)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        detail = (getattr(error, "stderr", None) or str(error)).strip() or str(error)
        emit(date=day, status="error", reason=detail.splitlines()[-1][:200])
        return 1
    conclusions = wait_for_crawl(slug, {r["databaseId"] for r in runs}, running, args.wait)
    branch.fetch()
    raw = read_records(branch, raw_path(day))
    if raw:
        status = "present"
    elif conclusions is None:
        status = "waiting"
    else:
        status = "crawl-failed" if "failure" in conclusions else "missing"
    emit(date=day, status=status, dispatched=not running, total=len(dedupe_by_id(raw)))
    return 0


# --- Claude Code local task ---------------------------------------------------


def cmd_status(args):
    branch = make_branch(args)
    branch.fetch()
    report = []
    for day in recent_days(branch, args.days):
        stats = counts(read_records(branch, raw_path(day)), read_records(branch, ai_path(day, args.language)))
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
    ingest.add_argument("--history-days", type=int, default=7)
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

    ensure = sub.add_parser("ensure-day", help="start the crawl if a weekday's papers are not published yet")
    ensure.add_argument("--date", help="UTC day, default today")
    ensure.add_argument("--wait", type=int, default=480, help="seconds to wait for the crawl")
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
