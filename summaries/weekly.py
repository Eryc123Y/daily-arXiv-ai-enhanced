"""Sunday's page: the week's daily reports on one page, with no model call.

Reads the `picks.json` that `digest` keeps for each reported day in its cache
folder, and lists the week's radar papers and how many picks each topic got,
with links to the week on the reading page.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from summaries import digest


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


def render_week(today, days, topics, site):
    start, end = days[0]["day"], days[-1]["day"]
    total = sum(d["total"] for d in days)
    lines = [f"# arXiv 本周回顾 · {start} 至 {end}", ""]
    lines += [f"本周 {len(days)} 天，共 {total} 篇 · [打开本周]({digest.day_link(site, end, start=start)})", ""]
    radar = [(d["day"], item, d["titles"]) for d in days for item in d["radar"]]
    lines.append(f"**本周雷达**（{len(radar)} 条）" if radar else "**本周雷达**：无")
    for day, item, titles in sorted(radar, key=lambda r: digest.LEVEL_ORDER[r[1]["level"]]):
        title = digest.shorten(titles.get(item["id"], item["id"]), digest.TITLE_CHARS)
        link = digest.day_link(site, day, topic="all", paper=item["id"])
        lines.append(f"- [{title}]({link})（{item['level']}，{day[5:]}）— {item['reason']}")
    lines += ["", "**各主题本周精选**"]
    for topic in topics:
        count = sum(len(d["topics"].get(topic["name"], [])) for d in days)
        lines.append(f"- {topic['name']}：{count} 篇 · [本周全部]({digest.day_link(site, end, topic=topic['name'], start=start)})")
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
    text, total, radar = render_week(today, days, digest.load_topics(), site)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    push = f"arXiv 本周：{total} 篇，雷达 {radar} 条。{digest.day_link(site, days[-1]['day'], start=days[0]['day'])}"
    digest.emit(status="written", path=str(report_path), push=push, report=text)
    return 0


def add_parser(sub):
    week = sub.add_parser("digest-week", help="Sunday: the week's reports on one page (no model call)")
    week.add_argument("--dir", required=True)
    week.add_argument("--today", help="report date (local), default today")
    week.add_argument("--force", action="store_true")
    week.add_argument("--site", help="reading page URL; default from the repository")
    week.add_argument("--cache", default=".cache/digest")
    week.set_defaults(func=cmd_digest_week)
