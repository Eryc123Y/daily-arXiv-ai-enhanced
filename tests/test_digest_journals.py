"""The daily report and Sunday's page on a mixed day: arXiv papers and journal papers from the feed (spec S1, R9)."""

import json

import pytest
from test_digest import (  # noqa: F401 (data_repo: autouse fixture)
    BRIEF,
    DAY,
    SITE,
    TOPICS,
    data_repo,
    make_vault,
    paper,
    run_digest,
)

from conftest import git, seed_data_branch
from summaries import abstracts, digest
from summaries.cli import main
from summaries.records import dump_jsonl

TCSVT_ID = "doi:10.1109/tcsvt.2026.1"
TOG_ID = "doi:10.1145/3842496"
TPAMI_ARXIV_ID = "2605.14526"  # a journal paper that also has an arXiv ID


def journal(paper_id, title, venue, tldr=None, has_abstract=True):
    record = {
        "id": paper_id,
        "source": "crossref",
        "title": title,
        "authors": ["B"],
        "venue": venue,
        "published": "2026-11-01",
        "doi": paper_id.removeprefix("doi:"),
        "oa_url": None,
        "url": f"https://doi.org/{paper_id.removeprefix('doi:')}",
        "categories": [],
        "has_abstract": has_abstract,
    }
    if tldr:
        record["AI"] = {f: tldr for f in ("tldr", "motivation", "method", "result", "conclusion")}
    return record


def mixed_day():
    """Two arXiv papers and four journal papers; abstracts of the journal papers are local, except the TPAMI one's."""
    raw = [
        paper("2611.1", "Stereo video", "A stereo method."),
        paper("2611.3", "Cats", "x"),
        journal(TCSVT_ID, "Depth for displays", "IEEE TCSVT"),
        journal(TOG_ID, "Hierarchical latents", "ACM TOG"),
        journal(TPAMI_ARXIV_ID, "Policy updates", "IEEE TPAMI", tldr="Uses RLVR with multiple epochs of data reuse.", has_abstract=False),
        journal("doi:10.1109/tip.2026.9", "Image restoration", "IEEE TIP"),
    ]
    local = {TCSVT_ID: "We convert monocular video to stereo pairs.", TOG_ID: "A latent for 3D shapes.", "doi:10.1109/tip.2026.9": "Denoising."}
    return raw, local


def mixed_candidates(known=frozenset()):
    raw, local = mixed_day()
    return digest.build_candidates(raw, [], TOPICS, digest.radar_patterns(BRIEF), set(known), local)


# --- Candidates ------------------------------------------------------------------


def test_journal_papers_match_topics_by_title_and_local_abstract_or_tldr():
    found = mixed_candidates()
    assert [r["id"] for r in found.by_topic["2D-to-3D and stereo"]] == ["2611.1", TCSVT_ID]
    assert [r["id"] for r in found.by_topic["Weak supervision and data reuse"]] == [TPAMI_ARXIV_ID]
    assert [r["id"] for r in found.radar] == [TPAMI_ARXIV_ID]
    assert [r["id"] for r in found.journal] == [TCSVT_ID, TPAMI_ARXIV_ID]
    assert {r["id"] for r in found.others} == {"2611.3", TOG_ID, "doi:10.1109/tip.2026.9"}
    assert found.venues == {"IEEE TCSVT": 1, "ACM TOG": 1, "IEEE TPAMI": 1, "IEEE TIP": 1}
    assert (found.total, found.arxiv_total) == (6, 2)


def test_the_local_abstract_is_used_only_for_journal_papers():
    raw = [paper("2611.1", "Cats", "x")]
    found = digest.build_candidates(raw, [], TOPICS, {}, set(), {"2611.1": "stereo"})
    assert found.by_topic["2D-to-3D and stereo"] == [] and found.journal == []


def test_an_arxiv_only_day_has_no_journal_candidates():
    found = digest.build_candidates([paper("2611.1", "Stereo video", "A stereo method.")], [], TOPICS, {}, set())
    assert found.journal == [] and found.venues == {} and found.arxiv_total == found.total == 1


# --- Writer prompt and answer ---------------------------------------------------------


def test_the_writer_sees_each_journal_papers_venue_and_the_journal_rule():
    prompt = digest.writer_prompt(DAY, mixed_candidates(), TOPICS, "", BRIEF)
    assert f"=== {TCSVT_ID} [IEEE TCSVT]\n" in prompt
    assert "abstract: We convert monocular video to stereo pairs." in prompt
    assert f"\n{TOG_ID} [ACM TOG] | Hierarchical latents |" in prompt
    assert "journal | <paper id> |" in prompt
    assert "2 new arXiv papers and 4 journal papers" in prompt


def test_an_arxiv_only_prompt_has_no_journal_rule():
    found = digest.build_candidates([paper("2611.1", "Stereo video", "A stereo method.")], [], TOPICS, {}, set())
    prompt = digest.writer_prompt(DAY, found, TOPICS, "", "")
    assert "journal" not in prompt.lower() and "1 new papers" in prompt


def test_journal_lines_name_journal_papers_only_and_respect_the_cap():
    found = mixed_candidates()
    text = "\n".join(
        [
            f"journal | {TCSVT_ID} | 单目转立体",
            "journal | 2611.1 | arXiv 论文不算期刊",
            f"journal | {TCSVT_ID} | 重复",
            f"journal | {TOG_ID} | 未匹配主题的期刊论文也可以",
            f"journal | {TPAMI_ARXIV_ID} | 超出上限",
        ]
    )
    journal_ids = {TCSVT_ID, TOG_ID, TPAMI_ARXIV_ID, "doi:10.1109/tip.2026.9"}
    picks, problems = digest.parse_picks(text, found.listed, [t["name"] for t in TOPICS], journal_ids=journal_ids)
    assert picks["journal"] == [(TCSVT_ID, "单目转立体"), (TOG_ID, "未匹配主题的期刊论文也可以")]
    assert problems == ["dropped: journal | 2611.1 | arXiv 论文不算期刊"]


def test_a_journal_pick_outside_the_keyword_matches_still_gets_the_section():
    raw = [paper("2611.1", "Cats", "x"), journal(TOG_ID, "Hierarchical latents", "ACM TOG")]
    found = digest.build_candidates(raw, [], TOPICS, {}, set(), {})
    picks = {"topics": {}, "radar": [], "other": [], "journal": [(TOG_ID, "三维潜表示")], "note": ""}
    lines = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE).splitlines()
    head = lines.index("**来自期刊**")
    assert lines[head + 1].endswith("（ACM TOG）— 三维潜表示")
    no_picks = digest.render_report(DAY, DAY, found, {**picks, "journal": []}, TOPICS, SITE)
    assert "来自期刊" not in no_picks


# --- Report ------------------------------------------------------------------------


def test_a_journal_papers_link_opens_it_on_the_page_with_its_id_encoded():
    assert digest.day_link(SITE, DAY, topic="all", paper=TCSVT_ID) == f"{SITE}#day={DAY}&topic=all&paper=doi%3A10.1109%2Ftcsvt.2026.1"


def mixed_report():
    found = mixed_candidates()
    picks = {
        "topics": {"2D-to-3D and stereo": [("2611.1", "立体视频方法"), (TCSVT_ID, "单目视频转立体")]},
        "radar": [{"id": TPAMI_ARXIV_ID, "level": "中", "reason": "复用轴相近", "check": False, "action": "", "read": False}],
        "other": [(TOG_ID, "三维潜表示")],
        "journal": [(TCSVT_ID, "已在主题下"), ],
        "note": "",
    }
    return digest.render_report(DAY, DAY, found, picks, TOPICS, SITE), found


def test_the_report_labels_journal_papers_with_their_venue():
    text, _ = mixed_report()
    tcsvt = f"[Depth for displays]({SITE}#day={DAY}&topic=2D-to-3D%20and%20stereo&paper=doi%3A10.1109%2Ftcsvt.2026.1)"
    assert f"- {tcsvt}（IEEE TCSVT）— 单目视频转立体" in text
    assert f"- [Stereo video]({SITE}#day={DAY}&topic=2D-to-3D%20and%20stereo&paper=2611.1) — 立体视频方法" in text
    assert "[Policy updates]" in text and "（IEEE TPAMI；中，仅摘要）— 复用轴相近" in text
    assert "（ACM TOG）— 三维潜表示" in text
    assert "arxiv.org" not in text and "alphaxiv" not in text.lower()


def test_the_report_header_counts_arxiv_and_journal_papers_apart():
    text, _ = mixed_report()
    assert f"**2 篇新论文 · 期刊 4 篇**（摘要 0/6）· [打开当天]({SITE}#day={DAY})" in text


def test_the_journal_section_lists_candidates_by_venue_and_journal_picks():
    found = mixed_candidates()
    picks = {"topics": {}, "radar": [], "other": [], "journal": [(TCSVT_ID, "单目视频转立体")], "note": ""}
    lines = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE).splitlines()
    head = lines.index("**来自期刊**（匹配 2 篇：IEEE TCSVT 1 · IEEE TPAMI 1）")
    assert lines[head + 1].startswith("- [Depth for displays](") and lines[head + 1].endswith("（IEEE TCSVT）— 单目视频转立体")


def test_a_journal_paper_shown_above_is_not_repeated_in_the_journal_section():
    text, _ = mixed_report()
    assert text.count("[Depth for displays]") == 1


def test_the_journal_section_comes_after_every_other_list():
    lines = mixed_report()[0].splitlines()
    head = next(n for n, line in enumerate(lines) if line.startswith("**来自期刊**"))
    assert lines.index("**其他**") < head
    assert all(not line.startswith("- ") for line in lines[head + 1 :])


def test_the_journal_line_counts_journal_papers_already_in_the_report():
    # TCSVT under a topic, TPAMI on the radar (both keyword matches), TOG under other (not a match)
    text, _ = mixed_report()
    assert "**来自期刊**：匹配 2 篇（IEEE TCSVT 1 · IEEE TPAMI 1），上面已列 3 篇期刊论文" in text
    assert "**来自期刊**：今日无精选" not in text


def test_the_journal_line_says_which_matches_are_already_above():
    found = mixed_candidates()
    picks = {"topics": {"2D-to-3D and stereo": [(TCSVT_ID, "单目视频转立体")]}, "radar": [], "other": [], "journal": [], "note": ""}
    text = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE)
    assert "**来自期刊**：匹配 2 篇（IEEE TCSVT 1 · IEEE TPAMI 1），其中 1 篇已列在上面" in text


def test_extra_journal_picks_keep_the_list_and_say_how_many_are_above():
    found = mixed_candidates()
    picks = {"topics": {"2D-to-3D and stereo": [(TCSVT_ID, "单目视频转立体")]}, "radar": [], "other": [], "journal": [(TPAMI_ARXIV_ID, "复用数据")], "note": ""}
    lines = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE).splitlines()
    head = lines.index("**来自期刊**（匹配 2 篇：IEEE TCSVT 1 · IEEE TPAMI 1；其中 1 篇已列在上面）")
    assert lines[head + 1].startswith("- [Policy updates](") and lines[head + 1].endswith("（IEEE TPAMI）— 复用数据")


def test_no_picks_only_when_no_journal_paper_is_in_the_report():
    found = mixed_candidates()
    picks = {"topics": {"2D-to-3D and stereo": [("2611.1", "立体视频方法")]}, "radar": [], "other": [], "journal": [], "note": ""}
    text = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE)
    assert "**来自期刊**：今日无精选（匹配 2 篇：IEEE TCSVT 1 · IEEE TPAMI 1）" in text


def test_an_arxiv_only_report_reads_as_before():
    found = digest.build_candidates([paper("1", "Stereo video", "A stereo method.")], [], TOPICS, {}, set())
    picks = {"topics": {"2D-to-3D and stereo": [("1", "g")]}, "radar": [], "other": [], "note": ""}
    text = digest.render_report(DAY, DAY, found, picks, TOPICS, SITE)
    assert "期刊" not in text and "**1 篇新论文**（摘要 0/1）" in text
    assert digest.push_message(DAY, found, picks, SITE).startswith("arXiv 11-02：1 篇。")


def test_the_push_message_counts_journal_papers_apart():
    found = mixed_candidates()
    picks = {"topics": {}, "radar": [], "other": [], "journal": [], "note": ""}
    assert digest.push_message(DAY, found, picks, SITE).startswith("arXiv 11-02：2 篇 + 期刊 4 篇。")


# --- Full text --------------------------------------------------------------------


def test_full_text_is_read_from_arxiv_only(tmp_path):
    found = mixed_candidates()
    picks = {
        "topics": {},
        "radar": [
            {"id": TCSVT_ID, "level": "中", "reason": "r", "check": True, "action": "", "read": False},
            {"id": TPAMI_ARXIV_ID, "level": "中", "reason": "r", "check": True, "action": "", "read": False},
        ],
        "other": [],
        "journal": [],
        "note": "",
    }
    fetched = []

    def fetch(paper_id, work):
        fetched.append(paper_id)
        return "body"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(digest, "fetch_fulltext", fetch)
        mp.setattr(digest, "run_model", lambda argv, prompt, cwd: f"radar | 可借鉴 | {TPAMI_ARXIV_ID} | 读过 | 引用\n")
        result = digest.deepen(picks, found, BRIEF, ["m"], tmp_path, tmp_path, [])
    assert fetched == [TPAMI_ARXIV_ID]  # the arXiv copy of a journal paper with an arXiv ID, never a publisher PDF
    assert [i["read"] for i in result["radar"]] == [False, True]


# --- Command -------------------------------------------------------------------------


def seed_mixed_day(tmp_path, remote, clone):
    raw, local = mixed_day()
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl(raw)})
    abstracts.save(clone / ".cache" / "summaries", local)


def test_digest_reports_a_mixed_day_and_keeps_the_weeks_journal_counts(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_mixed_day(tmp_path, remote, clone)
    vault = make_vault(tmp_path)
    writer = f"topic | 2D-to-3D and stereo | 2611.1 | 立体视频方法\njournal | {TCSVT_ID} | 单目视频转立体\nnote | 期刊有一篇立体\n"
    monkeypatch.chdir(clone)

    code, out, prompts = run_digest(clone, vault, monkeypatch, capsys, [writer])

    assert code == 0 and out["status"] == "written"
    assert "We convert monocular video to stereo pairs." in prompts[0]
    report = (vault / "digests" / f"{DAY}.md").read_text()
    assert "**来自期刊**（匹配 2 篇：IEEE TCSVT 1 · IEEE TPAMI 1）" in report and "（IEEE TCSVT）— 单目视频转立体" in report
    assert "We convert monocular" not in report  # the abstract stays local
    saved = json.loads((clone / ".cache" / "digest" / DAY / "picks.json").read_text())
    assert saved["journal"] == [[TCSVT_ID, "单目视频转立体"]]
    assert saved["journal_topics"] == {TCSVT_ID: ["2D-to-3D and stereo"]}
    assert saved["venues"] == {"IEEE TCSVT": 1, "ACM TOG": 1, "IEEE TPAMI": 1, "IEEE TIP": 1}
    assert "We convert monocular" not in json.dumps(saved)


def test_a_dry_run_writes_the_report_but_leaves_the_data_branch_alone(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_mixed_day(tmp_path, remote, clone)
    scratch = make_vault(tmp_path / "scratch")
    before = git(remote, "rev-parse", "data")
    monkeypatch.chdir(clone)
    monkeypatch.setattr(digest, "run_model", lambda argv, prompt, cwd: "note | 无\n")
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)

    code = main(["--repo", str(clone), "digest", "--dir", str(scratch), "--today", DAY, "--date", DAY, "--dry-run"])

    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["status"] == "written"
    assert (scratch / "digests" / f"{DAY}.md").exists()
    assert git(remote, "rev-parse", "data") == before
    assert (scratch / "work" / DAY / "picks.json").exists()


def test_the_week_counts_journal_picks_by_topic_and_journal_papers_by_venue(tmp_path, monkeypatch, capsys):
    from summaries import weekly

    vault = make_vault(tmp_path)
    monkeypatch.setattr(weekly, "read_log", lambda args: [])
    monkeypatch.setattr(digest, "load_topics", lambda: TOPICS)
    cache = tmp_path / "cache"
    days = [
        ("2026-10-30", {"2D-to-3D and stereo": [["2610.1", "g"]]}, [], {}, {}),
        ("2026-11-02", {"2D-to-3D and stereo": [[TCSVT_ID, "g"]]}, [[TOG_ID, "g"]], {TOG_ID: ["2D-to-3D and stereo"]}, {"IEEE TCSVT": 3, "ACM TOG": 5}),
        ("2026-11-03", {}, [], {}, {"ACM TOG": 2}),
    ]
    for day, topics, journal_picks, journal_topics, venues in days:
        (cache / day).mkdir(parents=True)
        saved = {"day": day, "total": 10, "topics": topics, "radar": [], "other": [], "note": "", "titles": {},
                 "journal": journal_picks, "journal_topics": journal_topics, "venues": venues}
        (cache / day / "picks.json").write_text(json.dumps(saved, ensure_ascii=False))

    code = main(["digest-week", "--dir", str(vault), "--today", "2026-11-03", "--cache", str(cache), "--site", SITE])

    text = (vault / "digests" / "2026-11-03.md").read_text()
    assert code == 0
    assert "- 2D-to-3D and stereo：3 篇 ·" in text
    assert "**本周期刊**：10 篇（ACM TOG 7 · IEEE TCSVT 3）" in text


def test_an_arxiv_only_week_has_no_journal_line(tmp_path, monkeypatch, capsys):
    from summaries import weekly

    days = [{"day": DAY, "total": 5, "topics": {}, "radar": [], "other": [], "note": "", "titles": {}}]
    text, _, _ = weekly.render_week(DAY, days, TOPICS, SITE)
    assert "期刊" not in text
