import json
import re

import pytest
from conftest import seed_data_branch

from summaries import digest
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
    path.write_text(path.read_text().rstrip("\n"))
    digest.append_radar_rows(path, DAY, found, picks)
    lines = path.read_text().splitlines()
    assert lines[0].startswith("| 日期 | arXiv ID |") and lines[1].startswith("|---")
    assert lines[2:] == [f"| {DAY} | 2611.00002 | T/x | 中 | a/b | {digest.UNREAD_ACTION} |"]


def test_rows_added_today_do_not_hide_papers_on_a_rerun(tmp_path):
    (tmp_path / "project-radar.md").write_text(f"| 2026-10-30 | 2610.12345 | T | 中 | x | y |\n| {DAY} | 2611.12345 | T | 中 | x | y |\n")
    assert digest.known_ids(tmp_path, today=DAY) == {"2610.12345"}


def test_a_broken_picks_file_does_not_stop_the_week(tmp_path, monkeypatch, capsys):
    vault = make_vault(tmp_path)
    cache = tmp_path / "cache"
    (cache / "2026-11-02").mkdir(parents=True)
    (cache / "2026-11-02" / "picks.json").write_text("{not json")
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)

    code = main(["digest-week", "--dir", str(vault), "--today", "2026-11-03", "--cache", str(cache), "--site", SITE])

    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "no-reports"
