import json
import re

import pytest
from conftest import git, seed_data_branch

from summaries import digest, weekly
from summaries.cli import main
from summaries.records import dump_jsonl

DAY = "2026-11-02"
SITE = "https://alice.github.io/my-arxiv/"
TOPICS = [
    {"name": "2D-to-3D and stereo", "keywords": ["stereo"]},
    {"name": "Weak supervision and data reuse", "keywords": ["RLVR"]},
]
BRIEF = """# brief

```
SUP  = verifiable reward|RLVR
REUSE= data reuse|multiple epochs
INFO = ideal observer
GROUND = word learning
候选 = ...
```

## 已知相关工作
- Known et al. (2605.25678)
"""


def paper(paper_id, title, summary="", tldr=None):
    record = {"id": paper_id, "title": title, "authors": ["A"], "categories": ["cs.LG"], "summary": summary}
    if tldr:
        record["AI"] = {f: tldr for f in ("tldr", "motivation", "method", "result", "conclusion")}
    return record


@pytest.fixture(autouse=True)
def data_repo(monkeypatch):
    monkeypatch.setenv("DATA_REPO", "alice/my-arxiv")


def test_radar_patterns_come_from_the_brief_and_need_context():
    patterns = digest.radar_patterns(BRIEF)
    assert set(patterns) == {"SUP", "REUSE", "INFO", "GROUND"}
    assert digest.is_radar_candidate("Training with multiple epochs of data", patterns)
    assert digest.is_radar_candidate("RLVR improves sample efficiency", patterns)
    assert not digest.is_radar_candidate("RLVR for math reasoning", patterns)
    assert not digest.is_radar_candidate("An ideal observer for vision", patterns)
    assert digest.is_radar_candidate("An ideal observer for label noise", patterns)
    assert digest.radar_patterns("no regex here") == {}


def test_known_ids_cover_the_radar_table_and_the_brief(tmp_path):
    (tmp_path / "project-radar.md").write_text("| 2026-10-30 | 2610.40564 | T | 中 | x | y |\n")
    (tmp_path / "project-brief.md").write_text(BRIEF)
    assert digest.known_ids(tmp_path) == {"2610.40564", "2605.25678"}


def test_candidates_group_keyword_and_radar_hits_and_skip_known_papers():
    raw = [
        paper("1", "Stereo video", "A stereo method."),
        paper("2", "RLVR at scale", "RLVR with multiple epochs."),
        paper("3", "Cats", "Nothing related."),
        paper("4", "Old news", "Data reuse again."),
    ]
    ai = [paper("1", "Stereo video", "A stereo method.", tldr="Short stereo summary.")]
    found = digest.build_candidates(raw, ai, TOPICS, digest.radar_patterns(BRIEF), known={"4"})
    assert [r["id"] for r in found.by_topic["2D-to-3D and stereo"]] == ["1"]
    assert [r["id"] for r in found.by_topic["Weak supervision and data reuse"]] == ["2"]
    assert [r["id"] for r in found.radar] == ["2"]
    assert [r["id"] for r in found.others] == ["3"]
    assert found.records["1"]["AI"]["tldr"] == "Short stereo summary."
    assert (found.total, found.done) == (4, 1)


def test_picks_keep_only_valid_lines_and_respect_the_caps():
    text = "\n".join(
        [
            "topic | 2D-to-3D and stereo | 1 | 立体视频方法",
            "topic | 2D-to-3D and stereo | 99 | 不在今天的列表里",
            "topic | Unknown topic | 1 | 未知主题",
            "radar | 中 | 2 | 复用与监督方式都比较了 | check",
            "radar | high | 3 | 英文等级也接受",
            "other | 3 | 其他高信号",
            "note | 今天立体论文少",
            "random chatter",
        ]
    )
    picks, problems = digest.parse_picks(text, {"1", "2", "3"}, [t["name"] for t in TOPICS])
    assert picks["topics"] == {"2D-to-3D and stereo": [("1", "立体视频方法")]}
    assert picks["radar"] == [
        {"id": "2", "level": "中", "reason": "复用与监督方式都比较了", "check": True, "action": "", "read": False},
        {"id": "3", "level": "高", "reason": "英文等级也接受", "check": False, "action": "", "read": False},
    ]
    assert picks["other"] == [("3", "其他高信号")]
    assert picks["note"] == "今天立体论文少"
    assert len(problems) == 2


def test_links_open_the_paper_on_the_reading_page():
    assert digest.day_link(SITE, DAY) == f"{SITE}#day={DAY}"
    assert digest.day_link(SITE, DAY, topic="2D-to-3D and stereo", paper="2610.1") == (
        f"{SITE}#day={DAY}&topic=2D-to-3D%20and%20stereo&paper=2610.1"
    )


def test_report_is_short_and_links_every_pick():
    raw = [paper("1", "Stereo video", "A stereo method."), paper("2", "RLVR at scale", "RLVR with multiple epochs.")]
    found = digest.build_candidates(raw, [], TOPICS, digest.radar_patterns(BRIEF), known=set())
    picks = {
        "topics": {"2D-to-3D and stereo": [("1", "立体视频方法")]},
        "radar": [{"id": "2", "level": "中", "reason": "撞在复用轴", "check": False, "action": "", "read": True}],
        "other": [],
        "note": "",
    }
    text = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE)
    assert text.startswith(f"# arXiv 日报 · {DAY}（周一）")
    assert f"**2 篇新论文**（摘要 0/2）· [打开当天]({SITE}#day={DAY})" in text
    assert f"[Stereo video]({SITE}#day={DAY}&topic=2D-to-3D%20and%20stereo&paper=1) — 立体视频方法" in text
    assert "[RLVR at scale]" in text and "（中，已读全文）" in text
    assert "Weak supervision and data reuse" in text
    assert len(text.splitlines()) < 30


def test_report_links_the_code_of_papers_that_release_it():
    raw = [
        {**paper("1", "Stereo video", "A stereo method."), "code_url": "https://github.com/a/stereo"},
        {**paper("2", "Stereo pages", "Another stereo method."), "code_url": "https://lab.github.io/pages"},
        paper("3", "Stereo plain", "A third stereo method."),
    ]
    found = digest.build_candidates(raw, [], TOPICS, {}, known=set())
    picks = {"topics": {"2D-to-3D and stereo": [("1", "a"), ("2", "b"), ("3", "c")]}, "radar": [], "other": [], "note": ""}
    lines = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE).splitlines()
    assert next(l for l in lines if "[Stereo video]" in l).endswith("— a · [代码](https://github.com/a/stereo)")
    assert next(l for l in lines if "[Stereo pages]" in l).endswith("— b · [项目页](https://lab.github.io/pages)")
    assert next(l for l in lines if "[Stereo plain]" in l).endswith("— c")


def test_the_writer_sees_which_candidates_release_code():
    raw = [{**paper("1", "Stereo video", "A stereo method."), "code_url": "https://github.com/a/stereo"}, paper("2", "Cats", "x")]
    found = digest.build_candidates(raw, [], TOPICS, {}, known=set())
    prompt = digest.writer_prompt(DAY, found, TOPICS, "", "")
    assert "=== 1 [code]\n" in prompt
    assert "\n2 | Cats |" in prompt


def test_a_radar_paper_is_not_repeated_under_its_topic():
    raw = [paper("2", "RLVR at scale", "RLVR with multiple epochs.")]
    found = digest.build_candidates(raw, [], TOPICS, digest.radar_patterns(BRIEF), known=set())
    picks = {
        "topics": {"Weak supervision and data reuse": [("2", "复用")]},
        "radar": [{"id": "2", "level": "可借鉴", "reason": "r", "check": False, "action": "", "read": False}],
        "other": [("2", "again")],
        "note": "",
    }
    text = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE)
    assert text.count("[RLVR at scale]") == 1
    assert "**Weak supervision and data reuse**：今日无精选" in text


def test_long_titles_are_shortened_in_the_report():
    found = digest.build_candidates([paper("1", "Stereo " + "x" * 200, "stereo")], [], TOPICS, {}, known=set())
    picks = {"topics": {"2D-to-3D and stereo": [("1", "g")]}, "radar": [], "other": [], "note": ""}
    link = next(line for line in digest.render_report(DAY, DAY, found, picks, TOPICS, SITE).splitlines() if line.startswith("- ["))
    assert len(link.split("](")[0].removeprefix("- [")) <= digest.TITLE_CHARS


def test_report_says_so_when_there_is_no_stereo_paper():
    found = digest.build_candidates([paper("3", "Cats", "x")], [], TOPICS, {}, known=set())
    empty = {"topics": {}, "radar": [], "other": [], "note": ""}
    text = digest.render_report(DAY, DAY, found, empty, TOPICS, SITE)
    assert "今日无 2D→3D / 立体视觉相关论文" in text
    assert "**雷达**：今日无可能撞车的论文" in text


def test_push_message_fits_a_notification():
    found = digest.build_candidates([paper("2", "R" * 300, "RLVR multiple epochs")], [], TOPICS, digest.radar_patterns(BRIEF), set())
    picks = {"topics": {}, "radar": [{"id": "2", "level": "高", "reason": "撞车", "check": False, "action": "", "read": False}], "other": [], "note": ""}
    message = digest.push_message(DAY, found, picks, SITE)
    assert len(message) <= 200
    assert message.startswith("arXiv 11-02：1 篇") and "雷达（高）" in message and f"#day={DAY}" in message


def make_vault(tmp_path):
    vault = tmp_path / "vault"
    (vault / "digests").mkdir(parents=True)
    (vault / "feedback.md").write_text("- 2026-10-28: 项目雷达放最前。\n")
    (vault / "project-brief.md").write_text(BRIEF)
    (vault / "project-radar.md").write_text("| 日期 | arXiv ID | 标题 | 等级 | 一句话关系 | 建议动作 |\n|---|---|---|---|---|---|\n")
    (vault / "ledger.md").write_text("# ledger\n")
    return vault


def run_digest(clone, vault, monkeypatch, capsys, answers, *extra, fulltext=None):
    prompts = []

    def fake_model(argv, prompt, cwd):
        prompts.append(prompt)
        return answers.pop(0)

    monkeypatch.setattr(digest, "run_model", fake_model)
    monkeypatch.setattr(digest, "fetch_fulltext", fulltext or (lambda paper_id, work: f"full text of {paper_id}"))
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)
    code = main(["--repo", str(clone), "digest", "--dir", str(vault), "--today", DAY, "--cache", str(clone / ".cache" / "digest"), *extra])
    return code, json.loads(capsys.readouterr().out), prompts


def seed_day(tmp_path, remote):
    raw = [paper("2611.1", "Stereo video", "A stereo method."), paper("2611.2", "RLVR at scale", "RLVR with multiple epochs."), paper("2611.3", "Cats", "x")]
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl(raw)})


def test_digest_writes_the_report_radar_rows_and_ledger(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)
    writer = "topic | 2D-to-3D and stereo | 2611.1 | 立体视频方法\nradar | 中 | 2611.2 | 复用轴相近 | check\n"
    deep = "radar | 可借鉴 | 2611.2 | 读完全文：只改复用，不比监督方式 | 引用并区分\n"

    code, out, prompts = run_digest(clone, vault, monkeypatch, capsys, [writer, deep])

    assert code == 0 and out["status"] == "written"
    report = (vault / "digests" / f"{DAY}.md").read_text()
    assert "[Stereo video]" in report and "（可借鉴，已读全文）" in report
    assert "项目雷达放最前" in prompts[0] and "2611.3 | Cats" in prompts[0]
    assert "full text of 2611.2" in prompts[1]
    assert "| 2611.2 | RLVR at scale | 可借鉴 | 读完全文：只改复用，不比监督方式 | 引用并区分 |" in (vault / "project-radar.md").read_text()
    ledger = (vault / "ledger.md").read_text()
    assert f"## {DAY}（网站数据 {DAY}）" in ledger and "项目雷达：2611.2" in ledger
    assert out["push"].startswith("arXiv 11-02：3 篇") and out["report"] == report
    log = [json.loads(line) for line in git(remote, "show", "data:logs/summary-runs.jsonl").splitlines()]
    assert (log[-1]["date"], log[-1]["path"]) == (DAY, "report")


def test_digest_does_not_rewrite_an_existing_report(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)
    (vault / "digests" / f"{DAY}.md").write_text("earlier\n")

    code, out, prompts = run_digest(clone, vault, monkeypatch, capsys, [])

    assert (code, out["status"], prompts) == (0, "exists", [])
    assert (vault / "digests" / f"{DAY}.md").read_text() == "earlier\n"


def test_a_day_already_reported_waits_for_a_new_batch(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)
    (vault / "ledger.md").write_text(f"## 2026-11-01（网站数据 {DAY}）\n")

    _, out, prompts = run_digest(clone, vault, monkeypatch, capsys, [])
    assert (out["status"], prompts) == ("no-new-batch", [])
    assert not (vault / "digests" / f"{DAY}.md").exists()

    _, out, _ = run_digest(clone, vault, monkeypatch, capsys, [], "--final")
    assert out["status"] == "written-no-batch"
    assert "arXiv 今天没有新批次" in (vault / "digests" / f"{DAY}.md").read_text()


def test_a_failed_full_text_download_keeps_the_abstract_grade(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)
    writer = "radar | 中 | 2611.2 | 复用轴相近 | check\n"

    def no_text(paper_id, work):
        return None

    code, out, prompts = run_digest(clone, vault, monkeypatch, capsys, [writer], fulltext=no_text)

    assert code == 0 and len(prompts) == 1
    assert "（中，仅摘要）" in (vault / "digests" / f"{DAY}.md").read_text()
    assert re.search(r"\| 2611\.2 \| .* \| 中 \| 复用轴相近 \| 仅摘要", (vault / "project-radar.md").read_text())


def test_week_review_collects_the_weeks_picks_without_a_model(tmp_path, monkeypatch, capsys):
    vault = make_vault(tmp_path)
    monkeypatch.setattr(weekly, "read_log", lambda args: [])  # no data branch in this test
    cache = tmp_path / "cache"
    for day, total, radar in [("2026-10-30", 910, []), ("2026-11-02", 450, [{"id": "2610.41073", "level": "可借鉴", "reason": "数值混杂", "check": False, "action": "", "read": False}])]:
        (cache / day).mkdir(parents=True)
        picks = {"day": day, "total": total, "topics": {"2D-to-3D and stereo": [["2610.1", "g"]]}, "radar": radar, "other": [], "note": "",
                 "titles": {"2610.1": "Stereo", "2610.41073": "bf16 Rounding"}}
        (cache / day / "picks.json").write_text(json.dumps(picks, ensure_ascii=False))
    (cache / "2026-10-20").mkdir()
    (cache / "2026-10-20" / "picks.json").write_text(json.dumps({"day": "2026-10-20", "total": 5, "topics": {}, "radar": [], "other": [], "note": "", "titles": {}}))
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)

    code = main(["digest-week", "--dir", str(vault), "--today", "2026-11-03", "--cache", str(cache), "--site", SITE])

    out = json.loads(capsys.readouterr().out)
    text = (vault / "digests" / "2026-11-03.md").read_text()
    assert code == 0 and out["status"] == "written"
    assert "本周 2 天，共 1360 篇" in text
    assert f"[bf16 Rounding]({SITE}#day=2026-11-02&topic=all&paper=2610.41073)（可借鉴，11-02）— 数值混杂" in text
    assert f"2D-to-3D and stereo：2 篇 · [本周全部]({SITE}#day=2026-11-02&from=2026-10-30&topic=2D-to-3D%20and%20stereo)" in text
    assert out["push"].startswith("arXiv 本周：1360 篇，雷达 1 条")


def test_an_answer_with_nothing_usable_writes_nothing_and_fails(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)

    code, out, _ = run_digest(clone, vault, monkeypatch, capsys, ["Please log in to continue.\n"])

    assert code == 1 and out["status"] == "error"
    assert not (vault / "digests" / f"{DAY}.md").exists()
    assert "网站数据" not in (vault / "ledger.md").read_text()


def test_picks_tolerate_list_markers_and_skip_repeated_radar_papers():
    text = "- topic | 2D-to-3D and stereo | 1 | g\n`radar | 中 | 2 | r`\n2. radar | 可借鉴 | 2 | again\n```\nnote | n\n"
    picks, _ = digest.parse_picks(text, {"1", "2"}, [t["name"] for t in TOPICS])
    assert picks["topics"] == {"2D-to-3D and stereo": [("1", "g")]}
    assert [i["id"] for i in picks["radar"]] == ["2"] and picks["note"] == "n"


def test_a_failed_full_text_call_keeps_the_abstract_grades(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)
    answers = ["radar | 中 | 2611.2 | 复用轴相近 | check\nnote | n\n"]

    def model(argv, prompt, cwd):
        if not answers:
            raise RuntimeError("claude timed out")
        return answers.pop(0)

    monkeypatch.setattr(digest, "run_model", model)
    monkeypatch.setattr(digest, "fetch_fulltext", lambda paper_id, work: "text")
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)
    code = main(["--repo", str(clone), "digest", "--dir", str(vault), "--today", DAY, "--cache", str(tmp_path / "c")])

    out = json.loads(capsys.readouterr().out)
    assert code == 0 and "（中，仅摘要）" in out["report"]
    assert any("claude timed out" in p for p in out["problems"])


def test_the_morning_report_waits_for_the_summaries(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)

    _, out, prompts = run_digest(clone, vault, monkeypatch, capsys, [], "--wait-summaries")
    assert (out["status"], prompts) == ("summaries-pending", [])

    _, out, _ = run_digest(clone, vault, monkeypatch, capsys, ["note | n\n"], "--wait-summaries", "--final")
    assert out["status"] == "written"


def test_radar_rows_go_into_a_well_formed_table_once(tmp_path):
    found = digest.build_candidates([paper("2611.00002", "T|x", "RLVR multiple epochs")], [], TOPICS, digest.radar_patterns(BRIEF), set())
    picks = {"topics": {}, "radar": [{"id": "2611.00002", "level": "中", "reason": "a|b", "check": False, "action": "", "read": False}], "other": [], "note": ""}
    path = tmp_path / "project-radar.md"
    digest.append_radar_rows(path, DAY, found, picks)
    digest.append_radar_rows(path, DAY, found, picks)
    path.write_text(path.read_text().rstrip("\n"))
    later = digest.build_candidates([paper("2611.00003", "U", "RLVR multiple epochs")], [], TOPICS, digest.radar_patterns(BRIEF), set())
    digest.append_radar_rows(path, DAY, later, {**picks, "radar": [{**picks["radar"][0], "id": "2611.00003"}]})
    lines = path.read_text().splitlines()
    assert lines[0].startswith("| 日期 | arXiv ID |") and lines[1].startswith("|---")
    assert lines[2:] == [
        f"| {DAY} | 2611.00002 | T/x | 中 | a/b | {digest.UNREAD_ACTION} |",
        f"| {DAY} | 2611.00003 | U | 中 | a/b | {digest.UNREAD_ACTION} |",
    ]


def test_rows_added_today_do_not_hide_papers_on_a_rerun(tmp_path):
    (tmp_path / "project-radar.md").write_text(f"| 2026-10-30 | 2610.12345 | T | 中 | x | y |\n| {DAY} | 2611.12345 | T | 中 | x | y |\n")
    assert digest.known_ids(tmp_path, today=DAY) == {"2610.12345"}


def test_week_health_lists_when_each_step_finished():
    log = [
        {"date": "2026-11-02", "path": "paused-no-key", "at": "2026-11-02T08:44:28+00:00", "total": 450, "done": 0, "pending": 450},
        {"date": "2026-11-02", "path": "claude-code", "at": "2026-11-02T13:59:36+00:00", "total": 450, "done": 450, "pending": 0},
        {"date": "2026-11-03", "path": "crawl", "at": "2026-11-03T10:58:28+00:00", "total": 1335, "added": 1335},
        {"date": "2026-11-03", "path": "local-claude", "at": "2026-11-03T13:44:44+00:00", "total": 1335, "done": 480, "pending": 855},
        {"date": "2026-11-03", "path": "local-claude", "at": "2026-11-03T14:00:55+00:00", "total": 1335, "done": 1335, "pending": 0},
        {"date": "2026-11-03", "path": "report", "at": "2026-11-03T14:01:53+00:00", "total": 1335, "done": 1335, "pending": 0},
    ]
    from datetime import timedelta, timezone

    lines = weekly.health_lines(log, ["2026-11-02", "2026-11-03"], timezone(timedelta(hours=8)))
    assert lines[0] == "**流程健康**（本地时间；数据入库 → 摘要写完 → 日报）"
    assert lines[1] == "- 11-02：— → 21:59（local Claude）→ —；暂停 1 次"
    assert lines[2] == "- 11-03：18:58 → 22:00（local Claude）→ 22:01"


def test_week_health_counts_reports_on_time_and_recent_misses():
    from datetime import timedelta, timezone

    def day(d, landed, report):
        return [
            {"date": d, "path": "crawl", "at": f"{d}T{landed}+00:00", "total": 9, "added": 9},
            {"date": d, "path": "report", "at": f"{d}T{report}+00:00", "total": 9, "done": 9, "pending": 0},
        ]

    log = day("2026-11-09", "01:20:00", "02:50:00") + day("2026-11-10", "01:20:00", "04:00:00") + day("2026-11-11", "10:58:00", "14:01:00")
    log += [{"date": "2026-11-12", "path": "crawl", "at": "2026-11-12T01:20:00+00:00", "total": 9, "added": 9}]
    days = weekly.week_days(log, ["2026-11-09", "2026-11-10", "2026-11-11"], "2026-11-15")
    assert days == ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"]
    lines = weekly.health_lines(log, days, timezone(timedelta(hours=8)), misses=(2, 1))
    # 11-09 on time (10:50); 11-10 late (12:00); 11-11 excluded, arXiv announced after 10:00; 11-12 never reported.
    assert "- 准时：1/3 天在 11:30 前写好日报（不计 arXiv 10:00 后才发布的日子）" in lines
    assert "- 11-12：09:20 → — → —" in lines
    assert "- 漏报（近 30 天）：2 篇，其中高或中 1 篇（missed.md）" in lines
    assert weekly.health_lines([], [], misses=(2, 1))[-1] == "- 漏报（近 30 天）：2 篇，其中高或中 1 篇（missed.md）"


def test_a_broken_picks_file_does_not_stop_the_week(tmp_path, monkeypatch, capsys):
    vault = make_vault(tmp_path)
    monkeypatch.setattr(weekly, "read_log", lambda args: [])  # no data branch in this test
    cache = tmp_path / "cache"
    (cache / "2026-11-02").mkdir(parents=True)
    (cache / "2026-11-02" / "picks.json").write_text("{not json")
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)

    code = main(["digest-week", "--dir", str(vault), "--today", "2026-11-03", "--cache", str(cache), "--site", SITE])

    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "no-reports"


def test_report_names_the_previous_batchs_hugging_face_favourites():
    found = digest.build_candidates([paper("3", "Cats", "x")], [], TOPICS, {}, known=set())
    empty = {"topics": {}, "radar": [], "other": [], "note": ""}
    hot = [("2026-10-30", "2610.5", "Popular paper", 40), ("2026-10-30", "2610.6", "Also liked", 12)]
    text = digest.render_report(DAY, DAY, found, empty, TOPICS, SITE, hot=hot)
    assert f"**HF 热门**（10-30 那批）：[Popular paper]({SITE}#day=2026-10-30&topic=all&paper=2610.5) ▲40；[Also liked]" in text


def test_digest_reads_upvotes_of_the_previous_batch(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(
        tmp_path,
        remote,
        {
            "data/2026-10-30.jsonl": dump_jsonl([paper("2610.5", "Popular paper"), paper("2610.6", "Quiet paper")]),
            "data/2026-10-30_hf.json": json.dumps({"2610.5": 40, "2610.6": 3}),
            f"data/{DAY}.jsonl": dump_jsonl([paper("2611.1", "Stereo video", "A stereo method.")]),
        },
    )
    vault = make_vault(tmp_path)

    code, out, _ = run_digest(clone, vault, monkeypatch, capsys, ["note | n\n"])

    assert code == 0 and "[Popular paper]" in out["report"] and "Quiet paper" not in out["report"]


def clients_model(calls, failing=("claude",)):
    """A run_model stand-in: clients named in `failing` fail as a signed-out claude does, the others answer in turn."""
    answers = ["radar | 中 | 2611.2 | 复用轴相近 | check\nnote | n\n", "radar | 可借鉴 | 2611.2 | 读完全文 | 引用\n"]

    def model(argv, prompt, cwd):
        calls.append(argv[0])
        if argv[0] in failing:
            raise RuntimeError(f"{argv[0]} exited with 1: Failed to authenticate: OAuth session expired")
        return answers.pop(0)

    return model


def run_with_clients(tmp_path, remote_and_clone, monkeypatch, capsys, model, *extra):
    remote, clone = remote_and_clone
    seed_day(tmp_path, remote)
    vault = make_vault(tmp_path)
    monkeypatch.setattr(digest, "run_model", model)
    monkeypatch.setattr(digest, "fetch_fulltext", lambda paper_id, work: "text")
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)
    code = main(["--repo", str(clone), "digest", "--dir", str(vault), "--today", DAY, "--cache", str(tmp_path / "c"), *extra])
    return code, json.loads(capsys.readouterr().out)


def test_codex_writes_the_report_when_claude_fails(tmp_path, remote_and_clone, monkeypatch, capsys):
    calls = []
    code, out = run_with_clients(tmp_path, remote_and_clone, monkeypatch, capsys, clients_model(calls))

    assert code == 0 and out["status"] == "written" and out["client"] == "codex"
    assert calls == ["claude", "codex", "codex"]  # the full-text check goes straight to the client that answered
    assert "（可借鉴，已读全文）" in out["report"]
    assert any("OAuth session expired" in p and "codex" in p for p in out["problems"])


def test_the_report_names_claude_when_it_answers(tmp_path, remote_and_clone, monkeypatch, capsys):
    calls = []
    code, out = run_with_clients(tmp_path, remote_and_clone, monkeypatch, capsys, clients_model(calls, failing=()))

    assert (code, out["client"], calls) == (0, "claude", ["claude", "claude"])
    assert not any("codex" in p for p in out["problems"])


@pytest.mark.parametrize("extra", [["--command", '["mycli", "{model}"]'], ["--fallback", ""]])
def test_no_fallback_with_an_explicit_client_or_an_empty_fallback(tmp_path, remote_and_clone, monkeypatch, capsys, extra):
    calls = []
    code, out = run_with_clients(tmp_path, remote_and_clone, monkeypatch, capsys, clients_model(calls, failing=("claude", "mycli")), *extra)

    assert out["status"] == "error" and "codex" not in calls and len(calls) == 1


def test_the_error_names_both_clients_when_both_fail(tmp_path, remote_and_clone, monkeypatch, capsys):
    calls = []
    code, out = run_with_clients(tmp_path, remote_and_clone, monkeypatch, capsys, clients_model(calls, failing=("claude", "codex")))

    assert out["status"] == "error" and calls == ["claude", "codex"]
    assert "claude exited" in out["reason"] and "codex exited" in out["reason"]


@pytest.mark.parametrize("value", ["not-json", "[]", "null", "[123]", '["codex", ""]'])
def test_a_malformed_fallback_is_refused_before_any_call(value, capsys):
    with pytest.raises(SystemExit):
        main(["digest", "--dir", "v", "--fallback", value])
    assert "--fallback" in capsys.readouterr().err


def test_an_unusable_fallback_answer_keeps_the_claude_error(tmp_path, remote_and_clone, monkeypatch, capsys):
    def model(argv, prompt, cwd):
        if argv[0] == "claude":
            raise RuntimeError("claude exited with 1: OAuth session expired")
        return "Sorry, I cannot produce the report."

    code, out = run_with_clients(tmp_path, remote_and_clone, monkeypatch, capsys, model)

    assert out["status"] == "error" and "OAuth session expired" in out["reason"] and "codex" in out["reason"]
