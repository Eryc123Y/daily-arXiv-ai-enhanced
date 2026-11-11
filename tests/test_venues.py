"""The public venue list, assets/venues.json: the watch list's names, kinds and areas for the page's Source selectors."""

import json

import pytest
from test_cli import branch_file, data_repo, paper, pipeline, run  # noqa: F401 (fixtures)

from conftest import git, seed_data_branch
from summaries import datafiles, feed
from summaries.databranch import PublishError, check_public
from summaries.records import dump_jsonl

AREAS = {
    "ML and vision": {"CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "ICLR", "AAAI", "IJCAI", "ACM MM",
                      "IEEE TPAMI", "IJCV", "IEEE TIP", "IEEE TCSVT", "JMLR", "TMLR"},
    "Graphics and VR": {"ACM TOG", "IEEE TVCG", "Computer Graphics Forum"},
    "NLP and linguistics": {"ACL", "EMNLP", "NAACL", "EACL", "TACL", "Computational Linguistics", "CoNLL",
                            "Mathematics of Language", "COLM"},
    "RL and AI": {"AAMAS", "JAAMAS", "JAIR", "Artificial Intelligence (Elsevier)", "RLC"},
    "Learning theory": {"COLT", "ALT", "AISTATS", "UAI", "Annals of Statistics", "SIMODS", "Information and Inference",
                        "Machine Learning (Springer)", "IEEE TIT"},
    "Logic and formal languages": {"LICS", "LMCS", "Journal of Automated Reasoning", "CPP", "ITP", "ICALP"},
    "Cognitive science": {"Cognitive Science", "Open Mind", "Computational Brain and Behavior", "Journal of Language Evolution"},
    "Neural networks and continual learning": {"CoLLAs", "Neural Computation", "Foundations and Trends in ML",
                                               "Nature Machine Intelligence", "Neural Networks", "IEEE TNNLS"},
    # Journal of Vision joins its sister journal Vision Research here; "Vision science" held only it.
    "3D, stereo and perception": {"3DV", "QoMEX", "IEEE TMM", "Vision Research", "Journal of Vision"},
    "Computational neuroscience": {"PLOS Computational Biology"},
}


def write_list(tmp_path, venues):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"venues": venues}))
    return path


# --- The watch list -------------------------------------------------------------


def test_every_watched_venue_has_one_of_the_areas():
    venues = feed.load_watchlist()

    by_area = {}
    for venue in venues:
        by_area.setdefault(venue["area"], set()).add(venue["name"])
    assert by_area == AREAS


def test_an_area_that_is_not_text_is_refused(tmp_path):
    with pytest.raises(feed.FeedError, match="area"):
        feed.load_watchlist(write_list(tmp_path, [{"name": "TIP", "kind": "journal", "group": "Journals", "area": 3}]))


def test_an_area_is_accepted_beside_the_other_fields(tmp_path):
    venue = {"name": "TIP", "kind": "journal", "group": "Journals", "area": "ML and vision"}
    assert feed.load_watchlist(write_list(tmp_path, [venue])) == [venue]


# --- The published summary -------------------------------------------------------


def test_the_summary_holds_name_kind_area_and_top_only_in_watch_list_order():
    summary = datafiles.venue_summary()

    assert summary[0] == {"name": "CVPR", "kind": "conference", "area": "ML and vision", "top": True}
    assert {"name": "ACM TOG", "kind": "journal", "area": "Graphics and VR", "top": True} in summary
    assert {"name": "EACL", "kind": "conference", "area": "NLP and linguistics", "top": False} in summary
    assert [v["name"] for v in summary] == [v["name"] for v in feed.load_watchlist()]
    assert all(set(v) == {"name", "kind", "area", "top"} for v in summary)


def test_a_venue_without_an_area_is_published_with_area_null_and_broken_entries_are_left_out(tmp_path):
    path = write_list(tmp_path, [
        {"name": "TIP", "kind": "journal", "group": "Journals", "issn": ["1057-7149"]},
        {"name": "", "kind": "journal"},
        {"name": "X", "kind": "magazine"},
        "not a venue",
    ])

    assert datafiles.venue_summary(path) == [{"name": "TIP", "kind": "journal", "area": None, "top": False}]


def test_a_venue_is_top_only_when_the_watch_list_says_true(tmp_path):
    path = write_list(tmp_path, [
        {"name": "A", "kind": "journal", "group": "x", "top": True},
        {"name": "B", "kind": "journal", "group": "x", "top": False},
        {"name": "C", "kind": "journal", "group": "x", "top": "yes"},
    ])

    assert [v["top"] for v in datafiles.venue_summary(path)] == [True, False, False]


def test_an_unreadable_watch_list_publishes_nothing(tmp_path):
    missing = tmp_path / "nowhere.json"
    broken = tmp_path / "broken.json"
    broken.write_text("{")

    assert datafiles.venue_settings(missing) == {}
    assert datafiles.venue_settings(broken) == {}


def test_venue_settings_is_the_public_file_as_json():
    files = datafiles.venue_settings()

    assert list(files) == ["assets/venues.json"]
    assert json.loads(files["assets/venues.json"]) == datafiles.venue_summary()
    check_public(files)


def test_the_venue_list_is_a_public_path_and_its_neighbours_are_not():
    check_public(["assets/venues.json"])
    for path in ("assets/venues.jsonl", "assets/watchlist.json", "venues.json"):
        with pytest.raises(PublishError):
            check_public([path])


def test_the_site_settings_carry_the_venue_list_even_without_categories(monkeypatch):
    monkeypatch.delenv("CATEGORIES", raising=False)
    assert set(datafiles.site_settings("English")) == {"assets/venues.json"}
    monkeypatch.setenv("CATEGORIES", "cs.CV")
    assert set(datafiles.site_settings("English")) == {"assets/site.json", "assets/venues.json"}


# --- Commits that keep it current -------------------------------------------------


def test_ingest_publishes_the_venue_list(tmp_path, remote_and_clone, capsys):
    remote, clone = remote_and_clone
    crawl = tmp_path / "crawl.jsonl"
    crawl.write_text(dump_jsonl([paper("A")]))

    run(clone, "ingest", "--date", "2026-10-30", "--input", str(crawl), capsys=capsys)

    assert json.loads(branch_file(remote, "assets/venues.json")) == datafiles.venue_summary()


def test_ensure_day_publishes_the_venue_list_once_when_nothing_else_changes(pipeline, capsys):  # noqa: F811 (pytest fixture argument)
    pipeline.seed({"2026-11-06": [paper("A")], "2026-11-09": [paper("B")]})

    code, out = pipeline.run(capsys=capsys)

    assert code == 0 and json.loads(out)["venues"] == "published" and pipeline.crawls == []
    assert json.loads(branch_file(pipeline.remote, "assets/venues.json")) == datafiles.venue_summary()
    head = git(pipeline.remote, "rev-parse", "data")

    code, out = pipeline.run(capsys=capsys)

    assert "venues" not in json.loads(out)
    assert git(pipeline.remote, "rev-parse", "data") == head


def test_ensure_day_replaces_a_stale_venue_list(tmp_path, pipeline, capsys):  # noqa: F811 (pytest fixture argument)
    seed_data_branch(tmp_path, pipeline.remote, {
        "data/2026-11-09.jsonl": dump_jsonl([paper("B")]),
        "data/2026-11-06.jsonl": dump_jsonl([paper("A")]),
        "assets/venues.json": "[]\n",
    })

    pipeline.run(capsys=capsys)

    assert json.loads(branch_file(pipeline.remote, "assets/venues.json")) == datafiles.venue_summary()
