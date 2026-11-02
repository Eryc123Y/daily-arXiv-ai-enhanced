"""Community signals from other platforms, kept beside each day's papers.

Hugging Face Daily Papers lists the arXiv papers its community upvotes each
day. `hf-signals` reads the lists of the last few days, keeps the upvotes of
papers that are in one of our days, and publishes them as
`data/<day>_hf.json` ({arXiv id: upvotes}, most upvoted first) on the data
branch. The page shows them as a badge and the daily report names the most
upvoted papers of the previous batch. No model and no key are involved.
"""

import json
from datetime import date, datetime, timedelta, timezone

import requests

from summaries import cli

HF_DAILY = "https://huggingface.co/api/daily_papers"
USER_AGENT = "daily-arxiv-signals/1.0 (+https://github.com/Eryc123Y/daily-arXiv-ai-enhanced)"


class SignalsUnavailable(RuntimeError):
    pass


def signals_path(day):
    return f"data/{day}_hf.json"


def fetch_hf_list(day):
    """The papers on Hugging Face's daily list for `day` (a UTC date)."""
    try:
        response = requests.get(HF_DAILY, params={"date": day, "limit": 100}, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        listing = response.json()
    except (requests.RequestException, ValueError) as error:
        raise SignalsUnavailable(f"Hugging Face list for {day}: {error}") from error
    return listing if isinstance(listing, list) else []


def hf_upvotes(days, fetch):
    """{arXiv id: upvotes} over the lists of `days`, keeping each paper's highest count."""
    upvotes = {}
    for day in days:
        try:
            listing = fetch(day)
        except SignalsUnavailable:
            continue
        for entry in listing:
            paper = entry.get("paper") or {}
            paper_id, count = paper.get("id"), paper.get("upvotes")
            if isinstance(paper_id, str) and isinstance(count, int):
                upvotes[paper_id] = max(count, upvotes.get(paper_id, 0))
    return upvotes


def read_signals(branch, day):
    try:
        return json.loads(branch.read(signals_path(day)) or "{}")
    except ValueError:
        return {}


def dump_signals(found):
    ordered = dict(sorted(found.items(), key=lambda item: (-item[1], item[0])))
    return json.dumps(ordered) + "\n"


def cmd_hf_signals(args):
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    lists = [(today - timedelta(days=n)).isoformat() for n in range(args.days)]
    upvotes = hf_upvotes(lists, fetch_hf_list)
    branch = cli.make_branch(args)
    branch.fetch()
    start = (today - timedelta(days=args.days + 7)).isoformat()
    days = sorted(d for p in branch.list_files("data/") if (m := cli.RAW_FILE.match(p)) and start <= (d := m.group(1)) <= today.isoformat())
    changed = []

    def build(current):
        files = {}
        changed.clear()
        for day in days:
            ids = {r["id"] for r in cli.read_records(current, cli.raw_path(day))}
            found = {paper_id: count for paper_id, count in upvotes.items() if paper_id in ids}
            if found and found != read_signals(current, day):
                files[signals_path(day)] = dump_signals(found)
                changed.append(day)
        return files

    if build(branch):
        branch.publish(build, f"signals: Hugging Face upvotes for {', '.join(changed)}")
    cli.emit(lists=len(lists), papers=len(upvotes), changed=list(changed))
    return 0


def add_parser(sub):
    hf = sub.add_parser("hf-signals", help="publish Hugging Face Daily Papers upvotes beside each day's papers")
    hf.add_argument("--days", type=int, default=7, help="how many of Hugging Face's daily lists to read")
    hf.add_argument("--today", help="UTC date of the newest list, default today")
    hf.set_defaults(func=cmd_hf_signals)
