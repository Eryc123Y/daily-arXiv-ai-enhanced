"""The feed inside ensure-day and the summary step, with tests/fixtures/fake_feed.py as FEED_COMMAND."""

import json
import sys
from datetime import UTC
from pathlib import Path

import pytest
from test_cli import FIELDS, branch_file, data_repo, ids_on, paper, pipeline, run  # noqa: F401 (fixtures)

from conftest import git
from summaries import digest
from summaries.records import dump_jsonl, parse_jsonl

FAKE_FEED = Path(__file__).parent / "fixtures" / "fake_feed.py"
TODAY = "2026-11-09"
CURSOR = "assets/feed-cursor.json"


def feed_line(n, published, abstract="An abstract.", **extra):
    return {
        "source": "crossref",
        "title": f"Journal paper {n} on binocular disparity",
        "authors": [f"Author{n} Family{n}"],
        "venue": "IEEE TIP",
        "published": published,
        "doi": f"10.1109/TIP.2026.{n}",
        "arxiv_id": None,
        "openreview_id": None,
        "abstract": abstract,
        "oa_url": None,
        "url": f"https://doi.org/10.1109/TIP.2026.{n}",
        **extra,
    }


@pytest.fixture
def feed(pipeline, tmp_path, monkeypatch):  # noqa: F811 (pytest fixture argument)
    """pipeline plus the fake feed: feed.lines are its output; feed.calls its arguments per call."""
    papers = tmp_path / "feed.jsonl"
    log = tmp_path / "feed-calls.jsonl"
    monkeypatch.setenv("FEED_COMMAND", json.dumps([sys.executable, str(FAKE_FEED)]))
    monkeypatch.setenv("FAKE_FEED_PAPERS", str(papers))
    monkeypatch.setenv("FAKE_FEED_LOG", str(log))
    monkeypatch.delenv("FAKE_FEED_FAIL", raising=False)

    def set_lines(lines):
        papers.write_text("".join((x if isinstance(x, str) else json.dumps(x)) + "\n" for x in lines))

    pipeline.set_lines = set_lines
    pipeline.calls = lambda: parse_jsonl(log.read_text()) if log.exists() else []
    pipeline.work = pipeline.clone / ".cache" / "summaries"
    monkeypatch.setattr("summaries.datafiles.datetime", _Frozen)
    set_lines([])
    return pipeline


def seed(pipeline, days, cursor=None):  # noqa: F811 (pytest fixture argument)
    files = {f"data/{d}.jsonl": dump_jsonl(rows) for d, rows in days.items()}
    if cursor:
        files[CURSOR] = json.dumps({"since": cursor, "at": f"{cursor}T08:00:00+00:00"})
    from conftest import seed_data_branch

    seed_data_branch(pipeline.clone.parent, pipeline.remote, files)


def report_of(out):
    return json.loads(out)


# --- R5: no key, no feed ----------------------------------------------------------


def test_without_a_feed_command_the_feed_is_skipped_and_arxiv_runs(pipeline, monkeypatch, capsys):  # noqa: F811 (pytest fixture argument)
    monkeypatch.delenv("FEED_COMMAND", raising=False)
    pipeline.seed({"2026-11-06": [paper("A")]})

    code, out = pipeline.run(capsys=capsys)

    report = report_of(out)
    assert code == 0 and report["feed"] == "skipped" and report["added"] == 2
    assert ids_on(pipeline.remote, TODAY) == ["B", "C"]


# --- R1: cursor -------------------------------------------------------------------


def test_a_run_after_five_missed_days_publishes_them_once_and_a_second_run_nothing(feed, capsys):
    seed(feed, {"2026-11-03": [paper("A")]}, cursor="2026-11-04")
    feed.recent = {"2026-11-04": [paper("D")], "2026-11-05": [paper("E")], "2026-11-06": [paper("F")]}
    feed.set_lines([feed_line(n, f"2026-11-0{n}") for n in range(4, 10)] + [feed_line(1, "2026-11-01")])

    code, out = feed.run(capsys=capsys)

    report = report_of(out)
    assert code == 0 and report["feed"]["status"] == "published"
    assert (report["feed"]["since"], report["feed"]["added"], report["feed"]["received"]) == ("2026-11-04", 6, 6)
    assert feed.calls()[0]["venues"].endswith("summaries/watchlist.json")
    feed_ids = [f"doi:10.1109/tip.2026.{n}" for n in range(4, 10)]
    assert ids_on(feed.remote, TODAY) == ["B", "C", *feed_ids]
    # The cursor moved in the commit that published the papers, and only there.
    moved = git(feed.remote, "log", "--format=%H", "data", "--", CURSOR).splitlines()[0]
    assert f"data/{TODAY}.jsonl" in git(feed.remote, "show", "--name-only", "--format=", moved)
    assert feed_ids[0] not in git(feed.remote, "show", f"{moved}^:data/{TODAY}.jsonl")
    assert json.loads(branch_file(feed.remote, CURSOR))["since"] == TODAY
    head = git(feed.remote, "rev-parse", "data")

    code, out = feed.run(capsys=capsys)

    report = report_of(out)
    assert code == 0 and report["feed"]["status"] == "nothing new" and report["feed"]["since"] == TODAY
    assert report["feed"]["received"] == 1 and report["feed"]["duplicates"] == 1
    assert git(feed.remote, "rev-parse", "data") == head


def test_the_first_run_looks_back_a_week(feed, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    feed.new = [paper("A")]  # arXiv has not announced today yet

    feed.run(capsys=capsys)

    assert f"data/{TODAY}.jsonl" not in git(feed.remote, "ls-tree", "-r", "--name-only", "data")  # no empty day file

    assert feed.calls()[0]["since"] == "2026-11-02"
    assert json.loads(branch_file(feed.remote, CURSOR))["since"] == TODAY


def test_a_failed_feed_leaves_the_cursor_and_does_not_stop_arxiv(feed, monkeypatch, capsys):
    seed(feed, {"2026-11-06": [paper("A")]}, cursor="2026-11-05")
    monkeypatch.setenv("FAKE_FEED_FAIL", "OpenAlex quota reached")

    code, out = feed.run(capsys=capsys)

    report = report_of(out)
    assert code == 0 and report["status"] == "present" and report["added"] == 2
    assert report["feed"] == {"status": "error", "since": "2026-11-05", "reason": "the feed command failed: OpenAlex quota reached"}
    assert json.loads(branch_file(feed.remote, CURSOR))["since"] == "2026-11-05"


def test_a_feed_command_that_is_not_a_json_list_is_an_error(feed, monkeypatch, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    monkeypatch.setenv("FEED_COMMAND", "litscout watch")

    code, out = feed.run(capsys=capsys)

    assert code == 0 and "JSON list" in report_of(out)["feed"]["reason"] and feed.calls() == []


def test_invalid_lines_are_dropped_with_a_count(feed, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    feed.set_lines([feed_line(1, "2026-11-08"), "{broken", feed_line(2, "2026-11-08", source="scihub"), feed_line(3, "2026-11-08", url="")])

    _, out = feed.run(capsys=capsys)

    assert (report_of(out)["feed"]["invalid"], report_of(out)["feed"]["added"]) == (3, 1)


def test_a_feed_paper_already_published_as_an_arxiv_paper_is_not_added(feed, capsys):
    seed(feed, {"2026-10-20": [paper("2610.00001")], "2026-11-06": [paper("A")]})
    feed.set_lines([feed_line(1, "2026-11-08", arxiv_id="2610.00001v2"), feed_line(2, "2026-11-08")])

    _, out = feed.run(capsys=capsys)

    assert report_of(out)["feed"]["duplicates"] == 1
    assert ids_on(feed.remote, TODAY) == ["B", "C", "doi:10.1109/tip.2026.2"]


def test_a_burst_is_published_over_several_runs_and_converges(feed, capsys):
    """Proceedings arrive as one batch: at most 150 a run, the cursor stays until the burst is through."""
    seed(feed, {"2026-11-06": [paper("A")]}, cursor="2026-11-05")
    feed.set_lines([feed_line(n, "2026-11-06") for n in range(1, 401)])
    reports = []

    for _ in range(3):
        _, out = feed.run(capsys=capsys)
        reports.append(report_of(out)["feed"])
        reports[-1]["cursor"] = json.loads(branch_file(feed.remote, CURSOR))["since"]

    assert [(r["added"], r["deferred"], r["cursor"]) for r in reports] == [
        (150, 250, "2026-11-05"),
        (150, 100, "2026-11-05"),
        (100, 0, TODAY),
    ]
    published = [i for i in ids_on(feed.remote, TODAY) if i.startswith("doi:")]
    assert len(published) == len(set(published)) == 400
    assert published[:3] == ["doi:10.1109/tip.2026.1", "doi:10.1109/tip.2026.2", "doi:10.1109/tip.2026.3"]


def test_the_cap_comes_from_the_environment(feed, monkeypatch, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    monkeypatch.setenv("FEED_MAX_PER_RUN", "2")
    feed.set_lines([feed_line(n, "2026-11-08") for n in range(1, 6)])

    _, out = feed.run(capsys=capsys)

    assert (report_of(out)["feed"]["added"], report_of(out)["feed"]["deferred"]) == (2, 3)


# --- Days without arXiv's papers ----------------------------------------------------


def test_feed_papers_alone_do_not_count_as_todays_arxiv_crawl(feed, capsys):
    """arXiv fails at the first run but the feed publishes; the next run still crawls arXiv."""
    from summaries import localcrawl

    seed(feed, {"2026-11-06": [paper("A")]})
    feed.set_lines([feed_line(1, "2026-11-08")])
    feed.new = localcrawl.CrawlError("the crawl returned no papers; arXiv may be unreachable")

    code, out = feed.run(capsys=capsys)
    assert code == 1 and report_of(out)["feed"]["added"] == 1

    feed.new = [paper("B")]
    code, out = feed.run(capsys=capsys)

    assert code == 0 and report_of(out)["added"] == 1
    assert ids_on(feed.remote, TODAY) == ["doi:10.1109/tip.2026.1", "B"]


def test_a_weekend_holds_feed_papers_only_and_does_not_hide_a_missed_friday(feed, capsys):
    seed(feed, {"2026-11-05": [paper("A")]})
    feed.today = "2026-11-07"
    feed.set_lines([feed_line(1, "2026-11-06")])

    _, out = feed.run(capsys=capsys)

    assert report_of(out)["status"] == "weekend" and ids_on(feed.remote, "2026-11-07") == ["doi:10.1109/tip.2026.1"]
    feed.today = TODAY
    feed.recent = {"2026-11-06": [paper("F")]}

    feed.run(capsys=capsys)

    assert feed.wanted[-1] == ["2026-11-06"] and ids_on(feed.remote, "2026-11-06") == ["F"]


def test_a_past_day_does_not_run_the_feed(feed, capsys):
    seed(feed, {"2026-11-05": [paper("A")], TODAY: [paper("B")]})
    feed.recent = {"2026-11-06": [paper("F")]}

    _, out = feed.run("--date", "2026-11-06", capsys=capsys)

    assert "feed" not in report_of(out) and feed.calls() == []


# --- R4: summaries -------------------------------------------------------------------


def status_of(clone, day, capsys):
    _, out = run(clone, "status", "--days", "30", capsys=capsys)
    return next(d for d in json.loads(out)["dates"] if d["date"] == day)


def test_a_mixed_day_end_to_end(feed, monkeypatch, capsys):
    """arXiv and feed papers on one day: the abstract stays local, both get summaries, the no-abstract one is listed only."""
    seed(feed, {"2026-11-06": [paper("A")]})
    feed.new = [paper("B")]
    feed.set_lines([feed_line(1, "2026-11-08", abstract="Private publisher abstract."), feed_line(2, "2026-11-08", abstract=None)])

    _code, out = feed.run(capsys=capsys)
    assert report_of(out)["feed"]["no_abstract"] == 1

    raw = branch_file(feed.remote, f"data/{TODAY}.jsonl")
    assert "Private publisher abstract" not in raw
    published = parse_jsonl(raw)[1]
    assert set(published) == {"id", "source", "title", "authors", "venue", "published", "doi", "oa_url", "url", "categories", "has_abstract"}
    assert [r.get("has_abstract") for r in parse_jsonl(raw)] == [None, True, False]
    assert status_of(feed.clone, TODAY, capsys) == {"date": TODAY, "total": 3, "done": 0, "pending": 2, "no_abstract": 1}

    _, out = run(feed.clone, "prepare", "--date", TODAY, capsys=capsys)
    plan = json.loads(out)
    chunk = Path(plan["chunks"][0]["input"]).read_text()
    assert "=== doi:10.1109/tip.2026.1\n" in chunk and "abstract: Private publisher abstract." in chunk
    assert "tip.2026.2" not in chunk and "=== B" in chunk
    Path(plan["chunks"][0]["output"]).write_text("".join(f"=== {i}\n" + FIELDS.format(n=1) + "\n" for i in ("B", "doi:10.1109/tip.2026.1")))
    _, out = run(feed.clone, "merge", "--date", TODAY, capsys=capsys)
    assert json.loads(out)["problems"] == []
    run(feed.clone, "finish", capsys=capsys)

    ai = parse_jsonl(branch_file(feed.remote, f"data/{TODAY}_AI_enhanced_English.jsonl"))
    assert [r["id"] for r in ai] == ["B", "doi:10.1109/tip.2026.1"]
    assert "summary" not in ai[1] and ai[1]["venue"] == "IEEE TIP"
    assert status_of(feed.clone, TODAY, capsys) == {"date": TODAY, "total": 3, "done": 2, "pending": 0, "no_abstract": 1}

    found = digest.build_candidates(parse_jsonl(raw), ai, [{"name": "stereo", "keywords": ["binocular"]}], {}, known=set())
    assert [p["id"] for p in found.by_topic["stereo"]] == ["doi:10.1109/tip.2026.1", "doi:10.1109/tip.2026.2"]
    assert "=== doi:10.1109/tip.2026.2 [IEEE TIP]\n" in digest.writer_prompt(TODAY, found, [{"name": "stereo", "keywords": ["binocular"]}], "", "")


def test_a_feed_paper_whose_local_abstract_is_gone_is_not_pending(feed, capsys):
    """Another machine or a cleared cache: the paper is listed, not left pending forever."""
    seed(feed, {"2026-11-06": [paper("A")]})
    feed.set_lines([feed_line(1, "2026-11-08")])
    feed.run(capsys=capsys)
    assert status_of(feed.clone, TODAY, capsys) == {"date": TODAY, "total": 3, "done": 0, "pending": 3}

    (feed.work / "abstracts.jsonl").unlink()

    assert status_of(feed.clone, TODAY, capsys) == {"date": TODAY, "total": 3, "done": 0, "pending": 2, "no_abstract": 1}


def test_the_digest_reads_no_full_text_for_a_feed_paper(monkeypatch):
    fetched = []
    monkeypatch.setattr(digest, "fetch_fulltext", lambda paper_id, work: fetched.append(paper_id))
    record = {"id": "doi:10.1/x", "source": "crossref", "title": "T", "authors": [], "venue": "TIP", "categories": []}
    found = digest.build_candidates([record], [], [], {}, known=set())
    picks = {"radar": [{"id": "doi:10.1/x", "check": True}]}

    assert digest.deepen(picks, found, "", ["x"], ".", ".", []) == picks
    assert fetched == []


class _Frozen:
    """datetime with now() fixed to TODAY, so `status` counts TODAY as recent."""

    @staticmethod
    def now(tz=None):
        from datetime import datetime

        return datetime(2026, 11, 9, 12, tzinfo=UTC)


def test_the_report_waits_for_the_days_arxiv_batch_not_its_feed_papers(feed, capsys):
    """arXiv late, feed papers already in today's file: the report must not mark today done before arXiv lands."""
    from summaries.datafiles import make_branch

    seed(feed, {"2026-11-06": [paper("A")]})
    feed.new = [paper("A")]  # /new still shows Friday's batch
    feed.set_lines([feed_line(1, "2026-11-08")])
    feed.run(capsys=capsys)
    branch = make_branch(type("Args", (), {"repo": str(feed.clone)})())
    branch.fetch()

    assert digest.newest_day(branch, TODAY, 3) == "2026-11-06"


def test_a_feed_radar_paper_is_written_once_and_then_known(tmp_path):
    """Radar rows and the known ids read doi: and openreview: ids too, not only arXiv-shaped ones."""
    record = {"id": "doi:10.1109/tip.2026.7", "source": "crossref", "title": "T", "authors": [], "venue": "TIP", "categories": []}
    found = digest.build_candidates([record], [], [], {}, known=set())
    picks = {"radar": [{"id": record["id"], "level": "高", "reason": "r", "action": "", "check": False}]}
    radar = tmp_path / "project-radar.md"

    digest.append_radar_rows(radar, "2026-11-09", found, picks)
    digest.append_radar_rows(radar, "2026-11-09", found, picks)

    assert radar.read_text().count("doi:10.1109/tip.2026.7") == 1
    assert digest.known_ids(tmp_path, "2026-11-10") == {"doi:10.1109/tip.2026.7"}


def test_a_feed_commit_carries_the_venue_list(feed, capsys):
    from summaries.datafiles import venue_summary

    seed(feed, {"2026-11-06": [paper("A")], TODAY: [paper("B")]}, cursor="2026-11-08")
    feed.set_lines([feed_line(5, "2026-11-08")])

    feed.run(capsys=capsys)

    commit = git(feed.remote, "log", "--format=%H", "data", "--", f"data/{TODAY}.jsonl").splitlines()[0]
    assert "assets/venues.json" in git(feed.remote, "show", "--name-only", "--format=", commit)
    assert json.loads(branch_file(feed.remote, "assets/venues.json")) == venue_summary()


# --- Topic-only venues ------------------------------------------------------------


def acl_line(n, title, abstract=None):
    """A paper of ACL, a `match: topics` venue of the shipped watch list."""
    return feed_line(n, "2026-11-08", abstract=abstract, title=title, venue="ACL", source="acl-anthology",
                     doi=f"10.18653/v1/2026.acl-long.{n}", url=f"https://aclanthology.org/2026.acl-long.{n}/")


def test_a_topic_only_venue_publishes_only_papers_on_eric_s_topics(feed, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    feed.set_lines([
        acl_line(1, "A sentiment dataset for tweets", "We annotate tweets."),
        acl_line(2, "Can transformers learn regular languages?"),
        acl_line(3, "Better prompts", "We study emergent communication between agents."),
        feed_line(4, "2026-11-08", title="A journal paper on nothing in particular"),
    ])

    _, out = feed.run(capsys=capsys)

    report = report_of(out)["feed"]
    assert (report["received"], report["added"], report["off_topic"]) == (4, 3, {"ACL": 1})
    published = ids_on(feed.remote, TODAY)
    assert "doi:10.18653/v1/2026.acl-long.1" not in published
    assert {"doi:10.18653/v1/2026.acl-long.2", "doi:10.18653/v1/2026.acl-long.3", "doi:10.1109/tip.2026.4"} <= set(published)


def test_off_topic_papers_are_dropped_before_the_cap_and_never_deferred(feed, monkeypatch, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    monkeypatch.setenv("FEED_MAX_PER_RUN", "1")
    feed.set_lines([acl_line(n, f"Tweets {n}", "We annotate tweets.") for n in range(1, 4)] + [feed_line(9, "2026-11-08")])

    _, out = feed.run(capsys=capsys)

    report = report_of(out)["feed"]
    assert (report["added"], report["deferred"], report["off_topic"]) == (1, 0, {"ACL": 3})
    assert json.loads(branch_file(feed.remote, CURSOR))["since"] == TODAY


def test_an_off_topic_abstract_is_not_kept_for_the_summaries(feed, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    feed.set_lines([acl_line(1, "Tweets", "We annotate tweets."), acl_line(2, "Regular languages", "On regular languages.")])

    feed.run(capsys=capsys)

    saved = (feed.work / "abstracts.jsonl").read_text(encoding="utf-8")
    assert "On regular languages." in saved and "We annotate tweets." not in saved


def test_the_report_has_an_empty_off_topic_count_when_nothing_was_dropped(feed, capsys):
    seed(feed, {"2026-11-06": [paper("A")]})
    feed.set_lines([feed_line(1, "2026-11-08")])

    _, out = feed.run(capsys=capsys)

    assert report_of(out)["feed"]["off_topic"] == {}
