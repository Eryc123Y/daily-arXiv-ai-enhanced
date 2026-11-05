import json

from conftest import seed_data_branch

from summaries import missed
from summaries.cli import main
from summaries.records import dump_jsonl

RADAR = """| 日期 | arXiv ID | 标题 | 等级 | 一句话关系 | 建议动作 |
|---|---|---|---|---|---|
| 2026-11-02 | 2610.41073 | Fair Cast | 可借鉴（强，已读 PDF） | r | a |
| 2026-11-08 | 2610.40564 | Single Algorithm | 中（回溯） | r | a |
| 2026-11-08 | 2402.03220 | Reusing batches | 可借鉴（回溯） | r | a |
"""


def test_backfill_rows_are_the_sunday_look_back_rows():
    rows = missed.backfill_rows(RADAR)
    assert [(r.found, r.paper_id, r.level) for r in rows] == [
        ("2026-11-08", "2610.40564", "中"),
        ("2026-11-08", "2402.03220", "可借鉴"),
    ]


def test_a_look_back_paper_we_had_in_a_batch_is_a_miss():
    rows = missed.backfill_rows(RADAR)
    found = missed.find_misses(rows, {"2610.40564": "2026-10-30"}, known=set())
    assert [(m.row.paper_id, m.listed) for m in found] == [("2610.40564", "2026-10-30")]
    assert missed.find_misses(rows, {"2610.40564": "2026-10-30"}, known={"2610.40564"}) == []


def test_recent_misses_count_the_last_thirty_days():
    text = missed.HEADER + (
        "| 2026-11-08 | 2610.40564 | T | 中 | 2026-10-30 | 周日回溯 |\n"
        "| 2026-11-01 | 2610.11111 | T | 可借鉴 | 2026-10-20 | Eric |\n"
        "| 2026-09-01 | 2608.11111 | T | 高 | 2026-08-20 | Eric |\n"
    )
    assert missed.recent_misses(text, "2026-11-08") == (2, 1)
    assert missed.recent_misses("", "2026-11-08") == (0, 0)


def test_missed_appends_new_misses_once(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    monkeypatch.setenv("DATA_REPO", "alice/my-arxiv")
    seed_data_branch(tmp_path, remote, {"data/2026-10-30.jsonl": dump_jsonl([{"id": "2610.40564", "title": "Single Algorithm"}])})
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "project-radar.md").write_text(RADAR)

    argv = ["--repo", str(clone), "missed", "--dir", str(vault), "--today", "2026-11-08"]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["added"] == 1
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)

    text = (vault / "missed.md").read_text()
    assert text.startswith(missed.HEADER)
    assert text.count("2610.40564") == 1
    assert "| 2026-11-08 | 2610.40564 | Single Algorithm | 中 | 2026-10-30 | 周日回溯 |" in text
    assert out == {"added": 0, "recent": 1, "recent_high_or_medium": 1}


def test_a_paper_listed_only_after_it_was_found_is_not_a_miss():
    rows = missed.backfill_rows(RADAR)
    assert missed.find_misses(rows, {"2610.40564": "2026-11-09"}, known=set()) == []


def test_escaped_pipes_in_a_hand_edited_title_keep_the_row():
    text = "| 2026-11-08 | 2610.40564 | A \\| B | 中（回溯） | r | a |\n"
    assert [(r.title, r.level) for r in missed.backfill_rows(text)] == [("A \\| B", "中")]


def test_an_old_batch_and_a_file_without_a_final_newline(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    monkeypatch.setenv("DATA_REPO", "alice/my-arxiv")
    seed_data_branch(tmp_path, remote, {"data/2026-06-01.jsonl": dump_jsonl([{"id": "2610.40564", "title": "Single Algorithm"}])})
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "project-radar.md").write_text(RADAR)
    (vault / "missed.md").write_text(missed.HEADER + "| 2026-11-01 | 2610.11111 | T | 高 | 2026-10-20 | Eric |")

    assert main(["--repo", str(clone), "missed", "--dir", str(vault), "--today", "2026-11-08"]) == 0
    out = json.loads(capsys.readouterr().out)

    lines = (vault / "missed.md").read_text().splitlines()
    assert lines[-2:] == ["| 2026-11-01 | 2610.11111 | T | 高 | 2026-10-20 | Eric |", "| 2026-11-08 | 2610.40564 | Single Algorithm | 中 | 2026-06-01 | 周日回溯 |"]
    assert out == {"added": 1, "recent": 2, "recent_high_or_medium": 2}


def test_rows_that_cannot_be_read_are_reported():
    text = RADAR + (
        "| 2610.40564 | 2026-11-08 | Columns swapped | 中（回溯） | r | a |\n"
        "| 2026-11-08 | 2610.22222 | Unknown level | 低（回溯） | r | a |\n"
        "not a table line\n"
    )
    assert missed.unreadable_rows(text) == [
        "| 2610.40564 | 2026-11-08 | Columns swapped | 中（回溯） | r | a |",
        "| 2026-11-08 | 2610.22222 | Unknown level | 低（回溯） | r | a |",
    ]
    assert missed.unreadable_rows(RADAR) == []
    assert missed.unreadable_rows(missed.HEADER) == []


def test_missed_warns_about_rows_it_skips(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    monkeypatch.setenv("DATA_REPO", "alice/my-arxiv")
    seed_data_branch(tmp_path, remote, {"data/2026-10-30.jsonl": dump_jsonl([{"id": "2610.40564", "title": "Single Algorithm"}])})
    vault = tmp_path / "vault"
    vault.mkdir()
    swapped = "| 2610.11111 | 2026-11-08 | Columns swapped | 高（回溯） | r | a |"
    (vault / "project-radar.md").write_text(RADAR + swapped + "\n")
    (vault / "missed.md").write_text(missed.HEADER + "| 11-01 | 2610.33333 | Short date | 中 | 2026-10-20 | Eric |\n")

    assert main(["--repo", str(clone), "missed", "--dir", str(vault), "--today", "2026-11-08"]) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)

    assert out["added"] == 1
    assert out["skipped"] == {"project-radar.md": [swapped], "missed.md": ["| 11-01 | 2610.33333 | Short date | 中 | 2026-10-20 | Eric |"]}
    assert "project-radar.md" in captured.err and "missed.md" in captured.err


def test_a_skipped_row_is_not_counted_and_does_not_block_a_valid_row():
    bad = "| 2026-11-07 | 2610.40564 | Single Algorithm | 低 | 2026-10-30 | Eric |"
    text = missed.HEADER + bad + "\n"
    assert missed.unreadable_rows(text) == [bad]
    assert missed.recent_misses(text, "2026-11-08") == (0, 0)
    rows = missed.backfill_rows(RADAR)
    known = {paper_id for _, paper_id, _, _ in missed._rows(text)}
    assert [m.row.paper_id for m in missed.find_misses(rows, {"2610.40564": "2026-10-30"}, known)] == ["2610.40564"]


def test_a_bad_row_mentioning_arxiv_id_is_not_taken_for_the_header():
    bad = "| 2610.40564 | 2026-11-08 | Why the arXiv ID is not enough | 中（回溯） | r | a |"
    assert missed.unreadable_rows(RADAR + bad + "\n") == [bad]
