"""assets/venue-days.json: how many journal and conference papers each day's raw file holds, for the page's weekly stream."""

import json

import pytest
from conftest import git, seed_data_branch
from test_cli import branch_file, data_repo, paper, pipeline, run  # noqa: F401 (fixtures)
from test_feed_pipeline import TODAY, feed, feed_line, seed  # noqa: F401 (fixtures)

from summaries import datafiles
from summaries.databranch import DataBranch, PublishError, check_public
from summaries.records import dump_jsonl

VENUE_DAYS = "assets/venue-days.json"


def venue(n, venue_name="ACM TOG", source="crossref"):
    return {"id": f"doi:10.1145/{n}", "source": source, "venue": venue_name, "title": f"V{n}", "authors": ["A"],
            "categories": [], "published": "2026-11-04"}


def published(remote):
    return json.loads(branch_file(remote, VENUE_DAYS))


def fetched(tmp_path, remote, clone, files):
    seed_data_branch(tmp_path, remote, files)
    branch = DataBranch(clone)
    branch.fetch()
    return branch


# --- What it holds ----------------------------------------------------------------


def test_a_raw_file_counts_its_records_that_are_not_from_arxiv():
    text = dump_jsonl([paper("A"), venue(1), venue(2, "ICLR", "openreview"), {**paper("B"), "source": "arxiv"}, venue(1)])

    assert datafiles.count_venue_papers(text) == 2  # the repeated id counts once
    assert datafiles.count_venue_papers(dump_jsonl([paper("A")])) == 0
    assert datafiles.count_venue_papers("") == 0
    with pytest.raises(ValueError):  # a broken raw file stops the commit, as reading it anywhere else does
        datafiles.count_venue_papers('{"source": "crossref", broken\n')


def test_the_counts_hold_only_days_with_venue_papers(tmp_path, remote_and_clone):
    remote, clone = remote_and_clone
    branch = fetched(tmp_path, remote, clone, {
        "data/2026-11-10.jsonl": dump_jsonl([paper("A")]),
        "data/2026-11-11.jsonl": dump_jsonl([paper("B"), venue(1), venue(2)]),
        "data/2026-11-14.jsonl": dump_jsonl([venue(3)]),  # a Saturday with feed papers only
        "data/2026-11-11_AI_enhanced_English.jsonl": dump_jsonl([venue(9)]),
    })

    assert datafiles.venue_day_counts(branch) == {"2026-11-11": 2, "2026-11-14": 1}


def test_files_about_to_be_committed_replace_the_branchs_copy(tmp_path, remote_and_clone):
    remote, clone = remote_and_clone
    branch = fetched(tmp_path, remote, clone, {"data/2026-11-11.jsonl": dump_jsonl([venue(1)])})

    counts = datafiles.venue_day_counts(branch, {
        "data/2026-11-11.jsonl": dump_jsonl([venue(1), venue(2)]),
        "data/2026-11-12.jsonl": dump_jsonl([venue(3)]),
        "logs/summary-runs.jsonl": "",
    })

    assert counts == {"2026-11-11": 2, "2026-11-12": 1}


def test_the_file_is_the_counts_and_nothing_else():
    files = datafiles.venue_days_file({"2026-11-14": 1, "2026-11-11": 187})

    assert list(files) == [VENUE_DAYS]
    assert json.loads(files[VENUE_DAYS]) == {"2026-11-11": 187, "2026-11-14": 1}
    assert list(json.loads(files[VENUE_DAYS])) == ["2026-11-11", "2026-11-14"]


def test_the_file_is_a_public_path_and_its_neighbours_are_not():
    check_public([VENUE_DAYS])
    for path in ("assets/venue-days.jsonl", "assets/venue-days.json.bak", "venue-days.json", "data/venue-days.json"):
        with pytest.raises(PublishError):
            check_public([path])


# --- Keeping it current in a commit -----------------------------------------------


def test_a_commit_recounts_the_days_it_writes_on_top_of_the_published_counts(tmp_path, remote_and_clone):
    remote, clone = remote_and_clone
    branch = fetched(tmp_path, remote, clone, {
        "data/2026-11-11.jsonl": dump_jsonl([venue(1)]),
        "data/2026-11-12.jsonl": dump_jsonl([venue(2)]),
        VENUE_DAYS: json.dumps({"2026-11-11": 1, "2026-11-12": 1}),
    })

    files = datafiles.with_venue_days(branch, {
        "data/2026-11-12.jsonl": dump_jsonl([paper("A")]),
        "data/2026-11-13.jsonl": dump_jsonl([venue(3), venue(4)]),
    })

    assert json.loads(files[VENUE_DAYS]) == {"2026-11-11": 1, "2026-11-13": 2}
    assert "data/2026-11-13.jsonl" in files


@pytest.mark.parametrize("stored", [None, "{not json", "[1, 2]", '{"2026-11-11": "many"}', '{"later": 3}'])
def test_without_readable_counts_a_commit_counts_every_day(tmp_path, remote_and_clone, stored):
    remote, clone = remote_and_clone
    files = {"data/2026-11-11.jsonl": dump_jsonl([venue(1), venue(2)])}
    if stored is not None:
        files[VENUE_DAYS] = stored
    branch = fetched(tmp_path, remote, clone, files)

    written = datafiles.with_venue_days(branch, {"data/2026-11-12.jsonl": dump_jsonl([paper("A")])})

    assert json.loads(written[VENUE_DAYS]) == {"2026-11-11": 2}


def test_a_commit_without_a_raw_file_leaves_the_counts_alone(tmp_path, remote_and_clone):
    remote, clone = remote_and_clone
    branch = fetched(tmp_path, remote, clone, {"data/2026-11-11.jsonl": dump_jsonl([venue(1)])})

    assert datafiles.with_venue_days(branch, {"logs/summary-runs.jsonl": ""}) == {"logs/summary-runs.jsonl": ""}


# --- The commands that write raw files --------------------------------------------


def test_ingest_counts_the_days_published_before_the_file_existed(tmp_path, remote_and_clone, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {"data/2026-11-11.jsonl": dump_jsonl([paper("A"), venue(1), venue(2)])})
    crawl = tmp_path / "crawl.jsonl"
    crawl.write_text(dump_jsonl([paper("B")]))

    run(clone, "ingest", "--date", "2026-11-12", "--input", str(crawl), capsys=capsys)

    assert published(remote) == {"2026-11-11": 2}
    commit = git(remote, "log", "--format=%H", "-1", "data")
    assert VENUE_DAYS in git(remote, "show", "--name-only", "--format=", commit)


def test_a_feed_commit_carries_the_counts(feed, capsys):  # noqa: F811 (pytest fixture argument)
    seed(feed, {"2026-11-06": [paper("A")], TODAY: [paper("B")]}, cursor="2026-11-08")
    feed.set_lines([feed_line(5, "2026-11-08"), feed_line(6, "2026-11-08")])

    feed.run(capsys=capsys)

    commit = git(feed.remote, "log", "--format=%H", "data", "--", f"data/{TODAY}.jsonl").splitlines()[0]
    assert VENUE_DAYS in git(feed.remote, "show", "--name-only", "--format=", commit)
    assert published(feed.remote) == {TODAY: 2}


def test_ensure_day_publishes_missing_counts_once(pipeline, capsys):  # noqa: F811 (pytest fixture argument)
    pipeline.seed({"2026-11-06": [paper("A"), venue(1)], "2026-11-09": [paper("B")]})

    pipeline.run(capsys=capsys)

    assert published(pipeline.remote) == {"2026-11-06": 1}
    head = git(pipeline.remote, "rev-parse", "data")
    pipeline.run(capsys=capsys)
    assert git(pipeline.remote, "rev-parse", "data") == head


def test_ensure_day_replaces_stale_counts(tmp_path, pipeline, capsys):  # noqa: F811 (pytest fixture argument)
    seed_data_branch(tmp_path, pipeline.remote, {
        "data/2026-11-09.jsonl": dump_jsonl([paper("B")]),
        "data/2026-11-06.jsonl": dump_jsonl([paper("A"), venue(1), venue(2)]),
        "data/2026-11-05.jsonl": dump_jsonl([paper("C")]),
        VENUE_DAYS: json.dumps({"2026-11-06": 1, "2026-11-05": 4}),
    })

    pipeline.run(capsys=capsys)

    assert published(pipeline.remote) == {"2026-11-06": 2}
