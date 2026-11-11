"""Sunday's page: the week's daily reports on one page, with no model call.

Reads the `picks.json` that `digest` keeps for each reported day in its cache
folder, and lists the week's radar papers and how many picks each topic got
(journal papers included), the week's journal papers by venue, with links to
the week on the reading page. Ends with the pipeline's health:
when each day's papers landed, its summaries finished and its report was
written, from logs/summary-runs.jsonl on the data branch.
"""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from summaries import datafiles, digest, missed
from summaries.records import parse_jsonl

ANNOUNCED_BY, ON_TIME_BY = time(10, 0), time(11, 30)  # the "report on time" measure in docs/ROADMAP.md
PATH_NAMES = {"claude-code": "local Claude", "local-claude": "local Claude", "api": "API", "api-fallback": "API fallback"}


def load_week(cache, today):
    """picks.json of the days in the seven days up to today, oldest first."""
    start = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    weeks = []
    for path in sorted(Path(cache).glob("*/picks.json")):
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(saved, dict) and start <= saved.get("day", "") <= today:
            weeks.append(saved)
    return weeks


def _clock(at, day, tz):
    moment = datetime.fromisoformat(at).astimezone(tz)
    return moment.strftime("%H:%M") if moment.date().isoformat() == day else moment.strftime("%m-%d %H:%M")


def _day_entries(log, day):
    """(crawl entry, first finished summary entry, report entry, number of pauses) of `day`."""
    entries = [e for e in log if e.get("date") == day and e.get("at")]

    def first(test):
        return next((e for e in entries if test(e)), None)

    done = first(lambda e: e.get("path") not in ("crawl", "report") and e.get("total") and not e.get("pending"))
    paused = sum(1 for e in entries if str(e.get("path", "")).startswith("paused"))
    return first(lambda e: e.get("path") == "crawl"), done, first(lambda e: e.get("path") == "report"), paused


def _local(entry, tz):
    return datetime.fromisoformat(entry["at"]).astimezone(tz)


def on_time(log, days, tz=None):
    """(days with the report by 11:30, days whose papers landed by 10:00): a late arXiv does not count against us."""
    hits = eligible = 0
    for day in days:
        landed, _, report, _ = _day_entries(log, day)
        if not landed or _local(landed, tz).date().isoformat() != day or _local(landed, tz).time() > ANNOUNCED_BY:
            continue
        eligible += 1
        written = report and _local(report, tz)
        hits += bool(written and written.date().isoformat() == day and written.time() <= ON_TIME_BY)
    return hits, eligible


def week_days(log, report_days, today):
    """The report days plus the week's days with papers but no report, which count as late."""
    start = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    crawled = {e["date"] for e in log if e.get("path") == "crawl" and start <= e.get("date", "") <= today}
    return sorted(set(report_days) | crawled)


def health_lines(log, days, tz=None, misses=None):
    """Per day: when the papers landed, the summaries finished and the report was written (local time); then the
    on-time count and, given `misses` as (recent, high or medium), the misses of the last thirty days."""
    lines = ["**流程健康**（本地时间；数据入库 → 摘要写完 → 日报）"]
    for day in days:
        landed, done, report, paused = _day_entries(log, day)
        if not (landed or done or report or paused):
            continue  # a day from before the log kept these entries

        def when(entry, day=day):
            return _clock(entry["at"], day, tz) if entry else "—"

        finished = f"{when(done)}（{PATH_NAMES.get(done['path'], done['path'])}）" if done else f"{when(done)} "
        note = f"；暂停 {paused} 次" if paused else ""
        lines.append(f"- {day[5:]}：{when(landed)} → {finished}→ {when(report)}{note}")
    hits, eligible = on_time(log, days, tz)
    if eligible:
        lines.append(f"- 准时：{hits}/{eligible} 天在 11:30 前写好日报（不计 arXiv 10:00 后才发布的日子）")
    if misses is not None:
        lines.append(f"- 漏报（近 30 天）：{misses[0]} 篇，其中高或中 {misses[1]} 篇（missed.md）")
    return lines


def read_log(args):
    """The data branch's run log, or [] when it cannot be read (offline, no clone)."""
    try:
        branch = datafiles.make_branch(args)
        branch.fetch()
        return parse_jsonl(branch.read(datafiles.RUN_LOG) or "")
    except Exception as error:  # the review page is still useful without its health table
        print(f"health table skipped: {error}")
        return []


def topic_count(saved, name):
    """Picks under the topic, plus the day's journal-section picks that matched it."""
    under = len(saved["topics"].get(name, []))
    journal_topics = saved.get("journal_topics", {})
    return under + sum(1 for pid, _ in saved.get("journal", []) if name in journal_topics.get(pid, []))


def journal_line(days):
    """The week's journal papers by venue, or None for an arXiv-only week."""
    venues = {}
    for saved in days:
        for venue, count in saved.get("venues", {}).items():
            venues[venue] = venues.get(venue, 0) + count
    if not venues:
        return None
    by_count = sorted(venues.items(), key=lambda item: (-item[1], item[0]))
    return f"**本周期刊**：{sum(venues.values())} 篇（{' · '.join(f'{venue} {n}' for venue, n in by_count)}）"


def render_week(today, days, topics, site, log=(), misses=None):
    start, end = days[0]["day"], days[-1]["day"]
    total = sum(d["total"] for d in days)
    lines = [f"# LitScout 本周回顾 · {start} 至 {end}", ""]
    lines += [f"本周 {len(days)} 天，共 {total} 篇 · [打开本周]({digest.day_link(site, end, start=start)})", ""]
    radar = [(d["day"], item, d["titles"]) for d in days for item in d["radar"]]
    lines.append(f"**本周雷达**（{len(radar)} 条）" if radar else "**本周雷达**：无")
    for day, item, titles in sorted(radar, key=lambda r: digest.LEVEL_ORDER[r[1]["level"]]):
        title = digest.shorten(titles.get(item["id"], item["id"]), digest.TITLE_CHARS)
        link = digest.day_link(site, day, topic="all", paper=item["id"])
        lines.append(f"- [{title}]({link})（{item['level']}，{day[5:]}）— {item['reason']}")
    lines += ["", "**各主题本周精选**"]
    for topic in topics:
        count = sum(topic_count(d, topic["name"]) for d in days)
        lines.append(f"- {topic['name']}：{count} 篇 · [本周全部]({digest.day_link(site, end, topic=topic['name'], start=start)})")
    journals = journal_line(days)
    if journals:
        lines += ["", journals]
    if log or misses is not None:
        lines += ["", *health_lines(log, week_days(log, [d["day"] for d in days], today), misses=misses)]
    return "\n".join(lines) + "\n", total, len(radar)


def cmd_digest_week(args):
    """Sunday: the week's report days, radar rows and topic counts in one page, with no model call."""
    vault = Path(args.dir)
    today = args.today or date.today().isoformat()
    report_path = vault / "digests" / f"{today}.md"
    if report_path.exists() and not args.force:
        digest.emit(status="exists", path=str(report_path))
        return 0
    days = load_week(args.cache, today)
    if not days:
        digest.emit(status="no-reports")
        return 0
    site = args.site or digest.site_url(args.repo)
    missed_path = vault / "missed.md"
    misses = missed.recent_misses(missed_path.read_text(encoding="utf-8"), today) if missed_path.exists() else None
    text, total, radar = render_week(today, days, digest.load_topics(), site, read_log(args), misses)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    push = f"LitScout 本周：{total} 篇，雷达 {radar} 条。{digest.day_link(site, days[-1]['day'], start=days[0]['day'])}"
    digest.emit(status="written", path=str(report_path), push=push, report=text)
    return 0


def add_parser(sub):
    week = sub.add_parser("digest-week", help="Sunday: the week's reports on one page (no model call)")
    week.add_argument("--dir", required=True)
    week.add_argument("--today", help="report date (local), default today")
    week.add_argument("--force", action="store_true")
    week.add_argument("--site", help="reading page URL; default from the repository")
    week.add_argument("--cache", default=digest.DEFAULT_CACHE)
    week.set_defaults(func=cmd_digest_week)
