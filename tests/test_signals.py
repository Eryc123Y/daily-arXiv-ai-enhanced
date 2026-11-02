import json

import pytest
from conftest import git, seed_data_branch

from summaries import signals
from summaries.cli import main
from summaries.records import dump_jsonl


@pytest.fixture(autouse=True)
def data_repo(monkeypatch):
    monkeypatch.setenv("DATA_REPO", "alice/my-arxiv")


def paper(paper_id):
    return {"id": paper_id, "title": f"T{paper_id}", "authors": ["A"], "categories": ["cs.LG"], "summary": "s"}


def listing(*entries):
    return [{"paper": {"id": paper_id, "upvotes": upvotes}, "title": f"T{paper_id}"} for paper_id, upvotes in entries]


def test_upvotes_keep_the_highest_count_across_lists():
    lists = {"2026-11-01": listing(("2611.1", 3)), "2026-11-02": listing(("2611.1", 9), ("2611.2", 4))}
    found = signals.hf_upvotes(["2026-11-01", "2026-11-02"], lambda day: lists.get(day, []))
    assert found == {"2611.1": 9, "2611.2": 4}


def test_a_list_that_cannot_be_read_is_skipped():
    def fetch(day):
        if day == "2026-11-01":
            raise signals.SignalsUnavailable("HTTP 503")
        return listing(("2611.1", 2))

    assert signals.hf_upvotes(["2026-11-01", "2026-11-02"], fetch) == {"2611.1": 2}


def run(clone, capsys, *argv):
    code = main(["--repo", str(clone), *argv])
    return code, json.loads(capsys.readouterr().out)


def test_hf_signals_publishes_the_upvotes_of_each_days_papers(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(
        tmp_path,
        remote,
        {
            "data/2026-10-30.jsonl": dump_jsonl([paper("2610.1"), paper("2610.2")]),
            "data/2026-11-02.jsonl": dump_jsonl([paper("2611.1")]),
        },
    )
    lists = {"2026-11-01": listing(("2610.2", 12), ("2609.9", 50)), "2026-11-02": listing(("2611.1", 3), ("2610.2", 15))}
    monkeypatch.setattr(signals, "fetch_hf_list", lambda day: lists.get(day, []))

    code, out = run(clone, capsys, "hf-signals", "--today", "2026-11-02", "--days", "3")

    assert code == 0 and out["changed"] == ["2026-10-30", "2026-11-02"]
    assert json.loads(git(remote, "show", "data:data/2026-10-30_hf.json")) == {"2610.2": 15}
    assert json.loads(git(remote, "show", "data:data/2026-11-02_hf.json")) == {"2611.1": 3}
    assert "_hf.json" not in git(remote, "show", "data:assets/file-list.txt")

    head = git(remote, "rev-parse", "data")
    code, out = run(clone, capsys, "hf-signals", "--today", "2026-11-02", "--days", "3")
    assert out["changed"] == [] and git(remote, "rev-parse", "data") == head
