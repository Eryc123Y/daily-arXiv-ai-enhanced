"""Papers the radar should have reported but did not, kept in DIGEST/missed.md.

A miss is a paper that was in one of our daily batches and turned up on the
radar only later: Sunday's look-back rows in project-radar.md (level ending in
"（回溯）") whose arXiv ID is in a data file, or a paper Eric points out in the
messenger chat (the messenger appends that row itself). Sunday's page counts the
misses of the last thirty days, one of the three measures in docs/ROADMAP.md.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from summaries import cli

HEADER = (
    "# 漏报清单\n\n"
    "<!-- 雷达本该报出、当时没报的论文。周日回溯由 `summaries missed` 追加；Eric 在送信员对话里指出的，由送信员追加一行。 -->\n\n"
    "| 发现日期 | arXiv ID | 标题 | 等级 | 当时所在的批次 | 来源 |\n"
    "|---|---|---|---|---|---|\n"
)
CELL = r"((?:\\\||[^|])*)"  # a table cell; a hand-edited "\|" stays inside it
ROW = re.compile(rf"^\|\s*(\d{{4}}-\d{{2}}-\d{{2}})\s*\|\s*(\d{{4}}\.\d{{4,5}})\s*\|{CELL}\|{CELL}\|")
LEVEL = re.compile(r"^(高|中|可借鉴)")
SERIOUS = ("高", "中")
RECENT_DAYS = 30


@dataclass(frozen=True)
class Row:
    found: str
    paper_id: str
    title: str
    level: str


@dataclass(frozen=True)
class Miss:
    row: Row
    listed: str


def _rows(text):
    for line in (text or "").splitlines():
        match = ROW.match(line)
        if match:
            found, paper_id, title, level = (part.strip() for part in match.groups())
            yield found, paper_id, title, level


def backfill_rows(radar_text):
    """The radar rows Sunday's look-back added, with their level without the "（回溯…）" note."""
    rows = []
    for found, paper_id, title, level in _rows(radar_text):
        grade = LEVEL.match(level)
        if "回溯" in level and grade:
            rows.append(Row(found, paper_id, title, grade.group(1)))
    return rows


def find_misses(rows, listed_on, known):
    """Rows whose paper was in a batch before it was found (`listed_on`: {id: first day}) and is not yet in missed.md."""
    return [
        Miss(row, listed_on[row.paper_id])
        for row in rows
        if row.paper_id in listed_on and listed_on[row.paper_id] < row.found and row.paper_id not in known
    ]


def recent_misses(text, today, days=RECENT_DAYS):
    """(misses found in the last `days` days, of them at level high or medium)."""
    start = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    recent = [level for found, _, _, level in _rows(text) if start < found <= today]
    return len(recent), sum(1 for level in recent if level.startswith(SERIOUS))


def listed_days(branch, ids, today):
    """{id: the first day's batch it was in} for `ids`, over every data file up to `today`."""
    found = {}
    for path in sorted(branch.list_files("data/")):
        match = cli.RAW_FILE.match(path)
        if not match or match.group(1) > today:
            continue
        for record in cli.read_records(branch, path):
            if record.get("id") in ids:
                found.setdefault(record["id"], match.group(1))
    return found


def _line(miss):
    title = miss.row.title.replace("|", "/")
    return f"| {miss.row.found} | {miss.row.paper_id} | {title} | {miss.row.level} | {miss.listed} | 周日回溯 |\n"


def cmd_missed(args):
    vault = Path(args.dir)
    today = args.today or date.today().isoformat()
    radar_path, missed_path = vault / "project-radar.md", vault / "missed.md"
    rows = backfill_rows(radar_path.read_text(encoding="utf-8") if radar_path.exists() else "")
    current = missed_path.read_text(encoding="utf-8") if missed_path.exists() else HEADER
    known = {paper_id for _, paper_id, _, _ in _rows(current)}
    misses = []
    if rows:
        branch = cli.make_branch(args)
        branch.fetch()
        misses = find_misses(rows, listed_days(branch, {r.paper_id for r in rows}, today), known)
    if misses or not missed_path.exists():
        current = current + ("" if current.endswith("\n") else "\n") + "".join(_line(m) for m in misses)
        missed_path.write_text(current, encoding="utf-8")
    total, serious = recent_misses(current, today)
    cli.emit(added=len(misses), recent=total, recent_high_or_medium=serious)
    return 0


def add_parser(sub):
    parser = sub.add_parser("missed", help="Sunday: record look-back radar papers that were in an earlier batch in missed.md")
    parser.add_argument("--dir", required=True, help="the digest folder (DIGEST)")
    parser.add_argument("--today", help="local date, default today")
    parser.set_defaults(func=cmd_missed)
