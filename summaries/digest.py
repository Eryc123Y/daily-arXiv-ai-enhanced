"""The daily report: a short Chinese digest of one day's papers, from the site's data.

Code selects what keywords can select: the reading page's interest topics,
the project brief's radar regex, and papers already reported. One model call
(Sonnet by default) reads those candidates plus every other paper's title and
TL;DR, and picks a few papers per topic and any possible radar collisions; a
second call reads the full text of at most two radar papers before they are
graded. Code renders the report with links into the reading page, appends the
radar rows and a ledger entry, and prints a push message.

The digest folder (--dir) holds feedback.md (standing preferences, given to
the model), project-brief.md (radar regex and collision levels),
project-radar.md and ledger.md (both appended), and digests/<today>.md.
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

from summaries import cli
from summaries.databranch import PublishError
from summaries.interests import load_topics, topics_for
from summaries.records import dedupe_by_id, has_summary
from summaries.signals import read_signals

WEEKDAYS = "一二三四五六日"
LEVELS = {"高": "高", "high": "高", "中": "中", "medium": "中", "可借鉴": "可借鉴", "borrow": "可借鉴", "无": None, "none": None}
LEVEL_ORDER = {"高": 0, "中": 1, "可借鉴": 2}
MAX_PER_TOPIC, MAX_RADAR, MAX_OTHER, MAX_DEEP = 3, 3, 2, 2
SNIPPET_CHARS, TITLE_CHARS = 160, 90
HOT_UPVOTES, HOT_PAPERS = 10, 2  # the previous batch's Hugging Face favourites named in the report
SUMMARISED_ENOUGH = 0.95  # --wait-summaries: a few papers left pending by failed chunks do not hold the report
ARXIV_ID = re.compile(r"\b\d{4}\.\d{4,5}\b")
RADAR_RULE = re.compile(r"^(SUP|REUSE|INFO|GROUND)\s*=\s*(.+)$", re.M)
SUP_CONTEXT = re.compile(r"efficien|sample|epoch|update|budget|compute|information|bits|scal", re.I)
INFO_CONTEXT = re.compile(r"supervis|label|feedback|reward", re.I)
LIST_MARKER = re.compile(r"^[\s>*`\-]*(?:\d+[.)]\s*)?")
PROJECT_PAGE = re.compile(r"^https?://[\w-]+\.git(?:hub|lab)\.io(?:/|$)", re.I)  # as in js/render.js
REFERENCES = re.compile(r"\n\s*(References|REFERENCES|Bibliography)\s*\n")
FULLTEXT_CHARS = 60_000
MODEL_TIMEOUT = 900
DEFAULT_COMMAND = ["claude", "-p", "--model", "{model}", "--tools", "", "--strict-mcp-config"]
USER_AGENT = "daily-arxiv-digest/1.0 (+https://github.com/Eryc123Y/daily-arXiv-ai-enhanced)"
NO_STEREO = "今日无 2D→3D / 立体视觉相关论文"
UNREAD_ACTION = "仅摘要；需要时读全文"
RADAR_HEADER = "| 日期 | arXiv ID | 标题 | 等级 | 一句话关系 | 建议动作 |\n|---|---|---|---|---|---|\n"


# --- Candidates ----------------------------------------------------------------


def radar_patterns(brief):
    """The brief's coarse regex (SUP, REUSE, INFO, GROUND), compiled; unusable lines are skipped."""
    patterns = {}
    for name, source in RADAR_RULE.findall(brief or ""):
        try:
            patterns[name] = re.compile(source.strip(), re.I)
        except re.error:
            continue
    return patterns


def is_radar_candidate(text, patterns):
    """The brief's rule: REUSE or GROUND; SUP with an efficiency word; INFO with a supervision word."""
    hit = {name for name, pattern in patterns.items() if pattern.search(text)}
    return bool(
        hit & {"REUSE", "GROUND"}
        or ("SUP" in hit and SUP_CONTEXT.search(text))
        or ("INFO" in hit and INFO_CONTEXT.search(text))
    )


def known_ids(folder, today=None):
    """arXiv IDs already in the radar table or the brief's known-work list.

    Rows dated `today` do not count, so a rerun of the same day sees its radar papers again.
    """
    ids = set()
    for name in ("project-radar.md", "project-brief.md"):
        path = Path(folder) / name
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            ids.update(i for line in lines if not (today and line.startswith(f"| {today} |")) for i in ARXIV_ID.findall(line))
    return ids


@dataclass
class Candidates:
    records: dict
    total: int
    done: int
    by_topic: dict
    radar: list
    others: list
    topics_of: dict = field(default_factory=dict)
    listed: set = field(default_factory=set)


def build_candidates(raw, ai_records, topics, patterns, known):
    summarised = {r["id"]: r for r in ai_records if has_summary(r)}
    papers = [summarised.get(p["id"], p) for p in dedupe_by_id(raw)]
    records = {p["id"]: p for p in papers}
    by_topic = {t["name"]: [] for t in topics}
    radar, others, topics_of = [], [], {}
    for paper in papers:
        names = topics_for(paper, topics)
        topics_of[paper["id"]] = names
        if paper["id"] in known:
            continue
        for name in names:
            by_topic[name].append(paper)
        is_radar = is_radar_candidate(f"{paper.get('title', '')} {paper.get('summary', '')}", patterns)
        if is_radar:
            radar.append(paper)
        if not names and not is_radar:
            others.append(paper)
    done = len(summarised.keys() & records.keys())
    return Candidates(records, len(papers), done, by_topic, radar, others, topics_of, set(records) - set(known))


# --- Model prompts and answers -----------------------------------------------------


def _one_line(text):
    return " ".join((text or "").split())


def _snippet(paper):
    tldr = (paper.get("AI") or {}).get("tldr")
    return shorten(tldr or paper.get("summary"), SNIPPET_CHARS)


def _code_tag(paper):
    return " [code]" if paper.get("code_url") and not PROJECT_PAGE.match(paper["code_url"]) else ""


def _block(paper):
    return f"=== {paper['id']}{_code_tag(paper)}\ntitle: {_one_line(paper.get('title'))}\nabstract: {_one_line(paper.get('summary'))}\n"


def writer_prompt(day, found, topics, feedback, brief):
    listed = set()
    sections = []
    for topic in topics:
        papers = found.by_topic.get(topic["name"], [])
        listed.update(p["id"] for p in papers)
        body = "\n".join(_block(p) for p in papers) or "(none)\n"
        sections.append(f"## {topic['name']} ({len(papers)})\n{body}")
    radar = [p for p in found.radar if p["id"] not in listed]
    topic_lines = "\n".join(f"- {t['name']}: {', '.join(t['keywords'])}" for t in topics)
    return f"""You choose papers for Eric's daily arXiv report, which is written in Chinese. Day: {day}, {found.total} new papers.
Read his standing preferences and the project brief, then the candidates.

Answer with plain lines and nothing else, each one of:
topic | <topic name exactly as listed> | <arXiv id> | <中文一句话要点，40 字以内>
radar | <高|中|可借鉴> | <arXiv id> | <中文一句话：可能撞在哪里，或能借鉴什么> | <check 或 ->
other | <arXiv id> | <中文一句话要点>
note | <可选：一句话总评>

Rules:
- At most {MAX_PER_TOPIC} topic lines per topic. His preferences decide how generous to be: for a topic he marks as a focus, include close secondary candidates (and say in the gist how they relate); for the others, only papers worth his time, and none is fine. A paper from any list may go under a topic it fits, not only keyword matches.
- Radar: grade with the brief's collision levels from what the abstract or TL;DR says; at most {MAX_RADAR} lines, the most relevant to the brief's claim and planned experiments first, none if nothing fits. 可借鉴 also covers confounds that would contaminate those experiments (numerical precision, sampler and trainer mismatch, hyperparameters not retuned per condition). Write `check` on at most {MAX_DEEP} lines whose grade needs the full text (high or medium candidates).
- other: at most {MAX_OTHER} high-signal papers that fit none of the topics.
- A paper appears once: a radar paper is not repeated under a topic or other.
- A gist states what the paper itself claims. Automatic video, geometry or spatial scores are not evidence of human stereo comfort.
- Use only arXiv IDs from the lists below. End with exactly one note line.

# Eric's standing preferences
{feedback.strip() or "(none)"}

# Project brief (radar)
{brief.strip() or "(none)"}

# Topics
{topic_lines}

Papers marked [code] link their code; between two papers of similar value, prefer the one with code.

# Keyword matches by topic
{chr(10).join(sections)}
# Radar regex hits not listed above
{chr(10).join(_block(p) for p in radar) or "(none)"}

# Every other paper today (id | title | TL;DR or start of abstract)
{chr(10).join(f"{p['id']}{_code_tag(p)} | {_one_line(p.get('title'))} | {_snippet(p)}" for p in found.others)}
"""


def deep_prompt(brief, papers):
    blocks = "\n".join(f"=== {p['id']}\ntitle: {_one_line(p.get('title'))}\nfull text:\n{text}\n" for p, text in papers)
    return f"""You check papers against Eric's research project before they go into his radar. For each paper below you have the main body of its full text.
Grade it with the brief's collision levels, say in one Chinese line where it collides or what to borrow, and give the suggested action (for example 引用并区分, 调整实验, 无需动作). Keep the paper's own claims apart from your inference.

Answer with one line per paper and nothing else:
radar | <高|中|可借鉴|无> | <arXiv id> | <中文一句话> | <建议动作>

# Project brief
{brief.strip()}

# Papers
{blocks}"""


def parse_picks(text, valid_ids, topic_names):
    """The writer's answer as {topics, radar, other, note}, and the lines it had to drop."""
    by_name = {name.lower(): name for name in topic_names}
    picks = {"topics": {}, "radar": [], "other": [], "note": ""}
    problems = []
    for raw_line in (text or "").splitlines():
        if raw_line.strip().startswith("```"):
            continue
        line = LIST_MARKER.sub("", raw_line).strip().strip("`")
        parts = [part.strip() for part in line.split("|")]
        kind = parts[0].lower()
        if kind == "topic" and len(parts) >= 4:
            name, paper_id, gist = by_name.get(parts[1].lower()), parts[2], parts[3]
            if not name or paper_id not in valid_ids:
                problems.append(f"dropped: {line.strip()}")
                continue
            chosen = picks["topics"].setdefault(name, [])
            if len(chosen) < MAX_PER_TOPIC:
                chosen.append((paper_id, gist))
        elif kind == "radar" and len(parts) >= 4:
            level, paper_id = LEVELS.get(parts[1].lower(), "?"), parts[2]
            if level in (None, "?") or paper_id not in valid_ids:
                problems.append(f"dropped: {line.strip()}")
                continue
            if paper_id in {item["id"] for item in picks["radar"]}:
                continue
            if len(picks["radar"]) < MAX_RADAR:
                check = len(parts) > 4 and parts[4].lower() == "check"
                picks["radar"].append({"id": paper_id, "level": level, "reason": parts[3], "check": check, "action": "", "read": False})
        elif kind == "other" and len(parts) >= 3:
            if parts[1] not in valid_ids:
                problems.append(f"dropped: {line.strip()}")
            elif len(picks["other"]) < MAX_OTHER:
                picks["other"].append((parts[1], parts[2]))
        elif kind == "note" and len(parts) >= 2:
            picks["note"] = parts[1]
    return picks, problems


def apply_deep_answer(picks, text):
    """Replace the graded radar items; a paper graded 无 leaves the radar."""
    graded = {}
    for line in (text or "").splitlines():
        parts = [part.strip() for part in line.split("|")]
        if parts[0].lower() == "radar" and len(parts) >= 4 and parts[1].lower() in LEVELS:
            graded[parts[2]] = (LEVELS[parts[1].lower()], parts[3], parts[4] if len(parts) > 4 else "")
    kept = []
    for item in picks["radar"]:
        if item["id"] in graded:
            level, reason, action = graded[item["id"]]
            if level is None:
                continue
            item = {**item, "level": level, "reason": reason, "action": action, "read": True}
        kept.append(item)
    return {**picks, "radar": kept}


# --- Full text ---------------------------------------------------------------


def main_body(text):
    match = REFERENCES.search(text)
    body = text[: match.start()] if match else text
    return re.sub(r"\n{3,}", "\n\n", body)[:FULLTEXT_CHARS]


def fetch_fulltext(paper_id, work):
    """The paper's main body from its arXiv PDF (needs pdftotext), or None."""
    pdf = Path(work) / f"{paper_id}.pdf"
    try:
        if not pdf.exists():
            response = requests.get(f"https://arxiv.org/pdf/{paper_id}", timeout=60, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                return None
            partial = pdf.with_suffix(".part")
            partial.write_bytes(response.content)
            partial.rename(pdf)
        result = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(pdf), "-"], capture_output=True, text=True, timeout=120, check=True
        )
    except subprocess.CalledProcessError:
        pdf.unlink(missing_ok=True)
        return None
    except (requests.RequestException, OSError, subprocess.SubprocessError):
        return None
    return main_body(result.stdout) or None


# --- Model calls ---------------------------------------------------------------


def model_argv(command, model):
    template = json.loads(command) if command else DEFAULT_COMMAND
    return [part.replace("{model}", model) for part in template]


def run_model(argv, prompt, cwd):
    """One headless call with the prompt on stdin; caching is off because nothing is reused."""
    try:
        result = subprocess.run(
            argv,
            input=prompt,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=MODEL_TIMEOUT,
            env={**os.environ, "DISABLE_PROMPT_CACHING": "1"},
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{argv[0]} gave no answer within {MODEL_TIMEOUT // 60} minutes") from error
    except OSError as error:
        raise RuntimeError(f"cannot run {argv[0]}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-1:] or [""]
        raise RuntimeError(f"{argv[0]} exited with {result.returncode}: {detail[0][:200]}")
    return result.stdout


def deepen(picks, found, brief, args, work, problems):
    """Read the full text of the radar papers marked `check` and regrade them.

    Without a PDF or an answer the abstract grades stay, marked 仅摘要.
    """
    papers = []
    for item in [i for i in picks["radar"] if i["check"]][:MAX_DEEP]:
        text = fetch_fulltext(item["id"], work)
        if text:
            papers.append((found.records[item["id"]], text))
    if not papers:
        return picks
    try:
        answer = run_model(model_argv(args.command, args.model), deep_prompt(brief, papers), args.repo)
    except RuntimeError as error:
        problems.append(f"full-text check failed: {error}")
        return picks
    (work / "deep.out.txt").write_text(answer, encoding="utf-8")
    return apply_deep_answer(picks, answer)


# --- Report ---------------------------------------------------------------------


def site_url(repo_dir):
    owner, name = cli.repo_slug(repo_dir).split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def day_link(site, day, topic=None, paper=None, start=None):
    params = [f"day={day}"]
    if start:
        params.append(f"from={start}")
    if topic:
        params.append(f"topic={quote(topic, safe='')}")
    if paper:
        params.append(f"paper={paper}")
    return f"{site}#{'&'.join(params)}"


def weekday(day):
    return WEEKDAYS[date.fromisoformat(day).weekday()]


def shorten(text, limit):
    text = _one_line(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _paper_link(site, day, found, paper_id, topic=None):
    names = found.topics_of.get(paper_id, [])
    chosen = topic if topic in names else (names[0] if names else "all")
    title = shorten(found.records[paper_id].get("title"), TITLE_CHARS).replace("[", "(").replace("]", ")")
    return f"[{title}]({day_link(site, day, topic=chosen, paper=paper_id)})"


def _code_link(found, paper_id):
    """' · [代码](url)' for a linked repository, ' · [项目页](url)' for a project page."""
    url = found.records[paper_id].get("code_url")
    if not url:
        return ""
    return f" · [{'项目页' if PROJECT_PAGE.match(url) else '代码'}]({url})"


def render_report(day, today, found, picks, topics, site, hot=()):
    """`hot`: (day, id, title, upvotes) of the previous batch's most upvoted papers on Hugging Face."""
    shown = {item["id"] for item in picks["radar"]}
    lines = [f"# arXiv 日报 · {today}（周{weekday(today)}）", ""]
    batch = "" if day == today else f"（arXiv {day} 批次）"
    lines += [f"**{found.total} 篇新论文**{batch}（摘要 {found.done}/{found.total}）· [打开当天]({day_link(site, day)})", ""]
    if hot:
        liked = "；".join(
            f"[{shorten(title, TITLE_CHARS)}]({day_link(site, d, topic='all', paper=pid)}) ▲{count}" for d, pid, title, count in hot
        )
        lines += [f"**HF 热门**（{hot[0][0][5:]} 那批）：{liked}", ""]
    if picks["radar"]:
        lines.append("**雷达**：")
        for item in sorted(picks["radar"], key=lambda i: LEVEL_ORDER[i["level"]]):
            seen = "已读全文" if item["read"] else "仅摘要"
            lines.append(f"- {_paper_link(site, day, found, item['id'])}（{item['level']}，{seen}）— {item['reason']}{_code_link(found, item['id'])}")
    else:
        lines.append("**雷达**：今日无可能撞车的论文")
    for index, topic in enumerate(topics):
        name = topic["name"]
        matched = len(found.by_topic.get(name, []))
        more = f"匹配 {matched} · [全部]({day_link(site, day, topic=name)})"
        chosen = [(pid, gist) for pid, gist in picks["topics"].get(name, []) if pid not in shown]
        shown.update(pid for pid, _ in chosen)
        lines.append("")
        if not chosen:
            empty = NO_STEREO if index == 0 and name.lower().startswith("2d") else "今日无精选"
            lines.append(f"**{name}**：{empty}（{more}）")
            continue
        lines.append(f"**{name}**（{more}）")
        lines += [f"- {_paper_link(site, day, found, pid, name)} — {gist}{_code_link(found, pid)}" for pid, gist in chosen]
    other = [(pid, gist) for pid, gist in picks["other"] if pid not in shown]
    if other:
        lines += ["", "**其他**"]
        lines += [f"- {_paper_link(site, day, found, pid)} — {gist}{_code_link(found, pid)}" for pid, gist in other]
    if picks["note"]:
        lines += ["", f"> {picks['note']}"]
    return "\n".join(lines) + "\n"


def push_message(day, found, picks, site):
    """One line under 200 characters: count, the strongest radar paper, picks, link."""
    head = f"arXiv {day[5:]}：{found.total} 篇。"
    picked = sum(len(items) for items in picks["topics"].values())
    tail = f"{f'精选 {picked} 篇。' if picked else ''} {day_link(site, day)}"
    if not picks["radar"]:
        return f"{head}雷达无命中。{tail}"
    top = min(picks["radar"], key=lambda i: LEVEL_ORDER[i["level"]])
    label = f"雷达（{top['level']}）："
    room = 200 - len(head) - len(label) - len("。") - len(tail)
    title = shorten(found.records[top["id"]].get("title", ""), max(room, 10))
    return f"{head}{label}{title}。{tail}"


def _cell(text):
    return _one_line(text).replace("|", "/")


def append_radar_rows(path, today, found, picks):
    """Add one table row per radar paper not already in the table."""
    path = Path(path)
    text = _read(path) or RADAR_HEADER
    present = set(ARXIV_ID.findall(text))
    rows = [
        f"| {today} | {item['id']} | {_cell(found.records[item['id']].get('title'))} | {item['level']} | "
        f"{_cell(item['reason'])} | {_cell(item['action'] or UNREAD_ACTION)} |\n"
        for item in picks["radar"]
        if item["id"] not in present
    ]
    if rows:
        path.write_text(text + ("" if text.endswith("\n") else "\n") + "".join(rows), encoding="utf-8")


def ledger_marker(day):
    return f"（网站数据 {day}）"


def picked_ids(picks):
    return [pid for items in picks["topics"].values() for pid, _ in items] + [pid for pid, _ in picks["other"]] + [
        item["id"] for item in picks["radar"]
    ]


def append_ledger(path, today, day, found, picks):
    radar = [i["id"] for i in picks["radar"]]
    chosen = [pid for pid in dict.fromkeys(picked_ids(picks)) if pid not in radar]
    entry = (
        f"\n## {today}{ledger_marker(day)}\n"
        f"- {datetime.now().strftime('%H:%M')} 运行；{found.total} 篇，摘要 {found.done}/{found.total}\n"
        f"- 入选：{', '.join(chosen) or '无'}\n"
        f"- 项目雷达：{', '.join(radar) or '无'}\n"
    )
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(entry)


# --- Command ------------------------------------------------------------------


def _read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def previous_hot(branch, day):
    """The most upvoted papers of the batch before `day`, from its data/<day>_hf.json."""
    earlier = sorted(d for p in branch.list_files("data/") if (m := cli.RAW_FILE.match(p)) and (d := m.group(1)) < day)
    if not earlier:
        return []
    prev = earlier[-1]
    upvotes = read_signals(branch, prev)
    titles = {r["id"]: r.get("title", "") for r in cli.read_records(branch, cli.raw_path(prev))}
    ranked = sorted(((n, pid) for pid, n in upvotes.items() if pid in titles and n >= HOT_UPVOTES), reverse=True)
    return [(prev, pid, titles[pid], n) for n, pid in ranked[:HOT_PAPERS]]


def newest_day(branch, today, days):
    start = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    found = (m.group(1) for p in branch.list_files("data/") if (m := cli.RAW_FILE.match(p)))
    candidates = sorted((d for d in found if start <= d <= today), reverse=True)
    return candidates[0] if candidates else None


def no_batch_note(today, day, site):
    latest = f"最近一批是 {day}，[在网站上看]({day_link(site, day)})。" if day else ""
    return f"# arXiv 日报 · {today}（周{weekday(today)}）\n\narXiv 今天没有新批次（节假日或批次推迟）。{latest}\n"


def emit(**values):
    print(json.dumps(values, ensure_ascii=False, indent=2))


def nothing_new(args, vault, today, day, site, report_path):
    """No unreported batch: say so, and on the day's last run leave a two-line note."""
    if not args.final:
        emit(status="no-new-batch", latest=day)
        return 0
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(no_batch_note(today, day, site), encoding="utf-8")
    emit(status="written-no-batch", path=str(report_path), push="")
    return 0


def choose(args, day, found, topics, brief, feedback, work):
    """The model's picks (writer call, then the full-text check), and the problems met."""
    prompt = writer_prompt(day, found, topics, feedback, brief)
    (work / "writer.prompt.txt").write_text(prompt, encoding="utf-8")
    answer = run_model(model_argv(args.command, args.model), prompt, args.repo)
    (work / "writer.out.txt").write_text(answer, encoding="utf-8")
    picks, problems = parse_picks(answer, found.listed, [t["name"] for t in topics])
    if not (picks["topics"] or picks["radar"] or picks["other"] or picks["note"]):
        raise RuntimeError(f"no usable lines in the answer (see {work / 'writer.out.txt'})")
    picks = deepen(picks, found, brief, args, work, problems)
    titles = {pid: found.records[pid].get("title", "") for pid in picked_ids(picks)}
    saved = {"day": day, "total": found.total, **picks, "titles": titles}
    (work / "picks.json").write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return picks, problems


def cmd_digest(args):
    vault = Path(args.dir)
    today = args.today or date.today().isoformat()
    report_path = vault / "digests" / f"{today}.md"
    if report_path.exists() and not args.force:
        emit(status="exists", path=str(report_path))
        return 0
    branch = cli.make_branch(args)
    branch.fetch()
    site = args.site or site_url(args.repo)
    day = args.date or newest_day(branch, today, args.days)
    if day is None or (ledger_marker(day) in _read(vault / "ledger.md") and not args.force):
        return nothing_new(args, vault, today, day, site, report_path)

    raw = cli.read_records(branch, cli.raw_path(day))
    ai_records = cli.read_records(branch, cli.ai_path(day, args.language))
    brief, feedback = _read(vault / "project-brief.md"), _read(vault / "feedback.md")
    topics = load_topics()
    found = build_candidates(raw, ai_records, topics, radar_patterns(brief), known_ids(vault, today))
    if args.wait_summaries and found.done < SUMMARISED_ENOUGH * found.total and not args.final:
        emit(status="summaries-pending", date=day, done=found.done, total=found.total)
        return 0
    work = Path(args.cache) / day
    work.mkdir(parents=True, exist_ok=True)
    try:
        picks, problems = choose(args, day, found, topics, brief, feedback, work)
    except RuntimeError as error:
        emit(status="error", date=day, reason=str(error))
        return 1

    # The ledger entry marks the day as reported, so it is written last.
    append_radar_rows(vault / "project-radar.md", today, found, picks)
    report = render_report(day, today, found, picks, topics, site, hot=previous_hot(branch, day))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    append_ledger(vault / "ledger.md", today, day, found, picks)
    try:
        cli.record_run(branch, day, args.language, "report")
    except (PublishError, subprocess.SubprocessError) as error:
        problems.append(f"run log not updated: {error}")
    emit(
        status="written",
        path=str(report_path),
        date=day,
        push=push_message(day, found, picks, site),
        report=report,
        problems=problems[:20],
    )
    return 0


def add_parser(sub):
    digest = sub.add_parser("digest", help="write the day's short Chinese report from the site data")
    digest.add_argument("--dir", required=True, help="digest folder (feedback.md, project-brief.md, digests/)")
    digest.add_argument("--date", help="arXiv day to report; default: the newest day of the last --days")
    digest.add_argument("--days", type=int, default=4)
    digest.add_argument("--today", help="report date (local), default today")
    digest.add_argument("--final", action="store_true", help="last run of the day: note a day without a new batch")
    digest.add_argument("--wait-summaries", action="store_true", help="wait while under 95%% of the day is summarised, unless --final")
    digest.add_argument("--force", action="store_true", help="rewrite today's report and report a day again")
    digest.add_argument("--model", default="sonnet")
    digest.add_argument("--command", help='headless client, JSON list with {model}; the prompt comes on stdin')
    digest.add_argument("--site", help="reading page URL; default from the repository")
    digest.add_argument("--cache", default=".cache/digest", help="work files (prompts, answers, picks)")
    digest.set_defaults(func=cmd_digest)
