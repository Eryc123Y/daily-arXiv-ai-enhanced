"""Command line for the daily pipeline.

Actions:      ingest (crawl -> data branch), mode, api (API-mode summaries)
Claude Code:  status, prepare, merge, finish (local summary task),
              handover (usage gate reached: API job or pause), record (run log)
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from summaries.blocks import format_chunk, parse_blocks
from summaries.databranch import DataBranch
from summaries.mode import resolve_mode
from summaries.providers import KEY_ENV, resolve_provider
from summaries.prompting import instructions
from summaries.records import (
    AI_FIELDS,
    dedupe_by_id,
    dump_jsonl,
    merge_summaries,
    parse_jsonl,
    pending_papers,
)

GITHUB_REMOTE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
SITE_SETTINGS = "assets/site.json"
RUN_LOG = "logs/summary-runs.jsonl"
API_WORKFLOW = "summarize-api.yml"
RAW_FILE = re.compile(r"^data/(\d{4}-\d{2}-\d{2})\.jsonl$")
LOCK_TTL_SECONDS = 3 * 3600


def parse_repo_slug(url):
    match = GITHUB_REMOTE.search(url.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def repo_slug(repo_dir):
    """owner/name of the GitHub repository: DATA_REPO, GITHUB_REPOSITORY, else the origin remote."""
    for name in ("DATA_REPO", "GITHUB_REPOSITORY"):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    url = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=str(repo_dir), capture_output=True, text=True
    ).stdout
    slug = parse_repo_slug(url)
    if not slug:
        raise SystemExit("Cannot tell which GitHub repository this is; set DATA_REPO=owner/name.")
    return slug


def site_settings(language):
    """Published to the data branch so the page knows the crawled categories."""
    categories = [c.strip() for c in os.environ.get("CATEGORIES", "").split(",") if c.strip()]
    if not categories:
        return {}
    return {SITE_SETTINGS: json.dumps({"categories": categories, "language": language}, indent=2) + "\n"}


def raw_path(day):
    return f"data/{day}.jsonl"


def ai_path(day, language):
    return f"data/{day}_AI_enhanced_{language}.jsonl"


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

    def build(current):
        existing = read_records(current, raw_path(args.date))
        combined = dedupe_by_id(existing + fresh)
        result.update(added=len(combined) - len(existing), papers=len(combined))
        return {raw_path(args.date): dump_jsonl(combined), **site_settings(args.language)}

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


def recent_days(branch, days):
    """Dates with a raw file in the last `days` days, newest first."""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    found = (m.group(1) for p in branch.list_files("data/") if (m := RAW_FILE.match(p)))
    return sorted((d for d in found if d >= cutoff), reverse=True)


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


# --- Run log and API fallback ------------------------------------------------


def gh(*args):
    """Run the GitHub CLI as the user it is logged in as."""
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


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


def cmd_record(args):
    branch = make_branch(args)
    emit(**record_run(branch, args.date, args.language, args.path, args.reason))
    return 0


class SettingsUnavailable(RuntimeError):
    pass


def gh_variable(slug, name):
    """A repository variable's value, "" when it is not set."""
    try:
        return gh("variable", "get", name, "-R", slug).strip()
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
        secrets = {s["name"] for s in json.loads(gh("secret", "list", "-R", slug, "--json", "name") or "[]")}
        env = {name: gh_variable(slug, name) for name in ("SUMMARY_PROVIDER", "SUMMARY_MODEL")}
    except subprocess.CalledProcessError as error:
        return f"could not read the repository secrets: {(error.stderr or str(error)).strip()}"
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
        slug = repo_slug(args.repo)
        problem = remote_api_problem(slug)
        if problem is None:
            gh("workflow", "run", API_WORKFLOW, "-R", slug, "-f", f"date={args.date}")
            path = "api-fallback"
        else:
            path = "paused-no-key"
    reason = "; ".join(filter(None, [args.reason, problem])) or None
    entry = record_run(make_branch(args), args.date, args.language, path, reason)
    emit(**entry, problems=merged["problems"])
    return 0


# --- Claude Code local task ---------------------------------------------------


def work_dir(args, day):
    return Path(args.work_dir) / day


def cmd_status(args):
    branch = make_branch(args)
    branch.fetch()
    report = []
    for day in recent_days(branch, args.days):
        stats = counts(read_records(branch, raw_path(day)), read_records(branch, ai_path(day, args.language)))
        report.append({"date": day, **stats})
    print(json.dumps({"dates": report}, ensure_ascii=False, indent=2))
    return 0


def acquire_lock(root, force):
    """Create the run lock atomically; return the current holder if it is taken."""
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "LOCK"
    if lock.exists() and (force or time.time() - lock.stat().st_mtime >= LOCK_TTL_SECONDS):
        lock.unlink(missing_ok=True)
    try:
        with open(lock, "x", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n")
    except FileExistsError:
        return lock.read_text(encoding="utf-8").strip() or "unknown"
    return None


def release_lock(root):
    (root / "LOCK").unlink(missing_ok=True)


def collect_outputs(directory):
    summaries, problems = {}, []
    for out in sorted(directory.glob("*.out.txt")):
        found, issues = parse_blocks(out.read_text(encoding="utf-8"))
        problems += [f"{out.name}: {issue}" for issue in issues]
        for paper_id, ai in found.items():
            summaries.setdefault(paper_id, ai)
    return summaries, problems


def cmd_merge(args):
    emit(**merge_outputs(args))
    return 0


def merge_outputs(args):
    directory = work_dir(args, args.date)
    outputs = sorted(directory.glob("*.out.txt")) if directory.exists() else []
    summaries, problems = collect_outputs(directory) if outputs else ({}, [])
    branch = make_branch(args)
    branch.fetch()
    known = {p["id"] for p in read_records(branch, raw_path(args.date))}
    unknown = sorted(set(summaries) - known)
    problems += [f"{paper_id}: not in the day's raw file" for paper_id in unknown]
    stats = publish_summaries(branch, args.date, args.language, summaries, "claude-code")
    archive = directory / "merged"
    for out in outputs:
        archive.mkdir(parents=True, exist_ok=True)
        out.rename(archive / f"{int(time.time())}-{out.name}")
    return {"date": args.date, "parsed": len(summaries), "problems": problems[:30], **stats}


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


def write_chunks(args):
    """Write INSTRUCTIONS.md and chunk inputs for the day's pending papers; return the plan."""
    directory = work_dir(args, args.date)
    leftovers = None
    if directory.exists() and any(directory.glob("*.out.txt")):
        leftovers = merge_outputs(args)
    for stale in directory.glob("*.in.txt") if directory.exists() else []:
        stale.unlink()
    directory.mkdir(parents=True, exist_ok=True)

    branch = make_branch(args)
    branch.fetch()
    raw = read_records(branch, raw_path(args.date))
    ai_records = read_records(branch, ai_path(args.date, args.language))
    todo = pending_papers(raw, ai_records)
    guide = directory / "INSTRUCTIONS.md"
    guide.write_text(subagent_instructions(args.language), encoding="utf-8")
    chunks = []
    for index in range(0, len(todo), args.chunk_size):
        part = todo[index : index + args.chunk_size]
        stem = directory / f"chunk-{index // args.chunk_size:03d}"
        Path(f"{stem}.in.txt").write_text(format_chunk(part), encoding="utf-8")
        chunks.append({"input": f"{stem}.in.txt", "output": f"{stem}.out.txt", "papers": len(part)})
    return {
        "date": args.date,
        **counts(raw, ai_records),
        "merged_leftovers": leftovers,
        "instructions": str(guide),
        "chunks": chunks,
    }


def cmd_finish(args):
    release_lock(Path(args.work_dir))
    for directory in Path(args.work_dir).glob("*/merged"):
        if directory.parent.name < (date.today() - timedelta(days=14)).isoformat():
            shutil.rmtree(directory.parent)
    print("lock released")
    return 0


def subagent_instructions(language):
    fields = "\n".join(f"{name}: ..." for name in AI_FIELDS)
    return f"""# Summarise arXiv papers

{instructions(language)}

## Input
The input file holds one block per paper: a line `=== <arXiv id>`, then a `title:` line and an `abstract:` line.

## Output
Use the Write tool to write the output file with one block per input paper, in input order, exactly in this format:

=== <arXiv id>
{fields}

Rules:
- Every paper in the input gets a block. Copy each `=== <arXiv id>` line exactly.
- Field names stay in English as shown; field contents are in {language}.
- Each field is a single line. No Markdown, no blank fields, nothing else in the file.

When the file is written, reply with only: done <number of blocks written>
"""


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

    from summaries import local_runner, setup

    local_runner.add_parser(sub)
    setup.add_parser(sub)

    handover = sub.add_parser("handover", help="usage gate reached: start the API job or pause")
    handover.add_argument("--date", required=True)
    handover.add_argument("--reason", help="why, e.g. 'weekly 81%%'")
    handover.set_defaults(func=cmd_handover)

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
