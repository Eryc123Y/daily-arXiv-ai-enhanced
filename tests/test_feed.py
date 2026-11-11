"""The feed's pieces without the data branch: watch list, line validation, ids and dedupe."""

import json
from difflib import SequenceMatcher
from itertools import combinations

import pytest

from summaries import dedupe, feed, shapes
from summaries.records import is_arxiv


def line(**overrides):
    base = {
        "source": "openalex",
        "title": "Stereo Video from Monocular Clips",
        "authors": ["Ada Lovelace", "Alan Turing"],
        "venue": "IEEE TCSVT",
        "published": "2026-11-05",
        "doi": "10.1109/TCSVT.2026.1234567",
        "arxiv_id": None,
        "openreview_id": None,
        "abstract": "We convert monocular clips to stereo.",
        "oa_url": None,
        "url": "https://doi.org/10.1109/TCSVT.2026.1234567",
    }
    return json.dumps({**base, **overrides})


# --- Watch list ---------------------------------------------------------------


def test_watch_list_v1_holds_the_specs_nineteen_venues():
    venues = feed.load_watchlist()

    names = [v["name"] for v in venues]
    assert len(names) == 19 and len(set(names)) == 19
    for name in ("CVPR", "ICLR", "ACM TOG", "IEEE TCSVT", "TMLR", "Journal of Vision"):
        assert name in names
    assert {v["kind"] for v in venues} == {"conference", "journal"}


def test_every_journal_names_its_openalex_source_and_issns():
    """The feed command resolves venues from these (values from the Phase 0 measurement)."""
    venues = {v["name"]: v for v in feed.load_watchlist()}

    for venue in venues.values():
        if venue["kind"] == "journal":
            assert venue["openalex_source"].startswith("S") and venue["issn"], venue["name"]
    assert venues["IEEE TIP"]["issn"] == ["1057-7149", "1941-0042"]
    assert "openalex_source" not in venues["ECCV"]  # inside LNCS; found by container title
    assert "ICLR.cc/2026/Conference" in venues["ICLR"]["openreview_venues"]


def write_list(tmp_path, venues):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"venues": venues}))
    return path


def test_watch_list_refuses_a_source_outside_the_lawful_three(tmp_path):
    """R6: only official APIs; a venue configured with any other source fails to load."""
    path = write_list(tmp_path, [{"name": "TIP", "kind": "journal", "group": "Journals", "sources": ["scihub"]}])

    with pytest.raises(feed.FeedError, match="scihub"):
        feed.load_watchlist(path)


@pytest.mark.parametrize(
    "venue",
    [
        {"name": "TIP", "kind": "magazine", "group": "Journals"},
        {"name": "", "kind": "journal", "group": "Journals"},
        {"name": "TIP", "kind": "journal", "group": "Journals", "scrape_url": "https://example.org"},
        {"name": "TIP", "kind": "journal", "group": "Journals", "issn": "1057-7149"},
        {"name": "TIP", "kind": "journal", "group": "Journals", "issn": [1057]},
        {"name": "ICLR", "kind": "conference", "group": "x", "openreview_venues": "ICLR.cc/2026/Conference"},
        {"name": "TIP", "kind": "journal", "group": "Journals", "openalex_source": ""},
    ],
)
def test_watch_list_refuses_bad_entries(tmp_path, venue):
    with pytest.raises(feed.FeedError):
        feed.load_watchlist(write_list(tmp_path, [venue]))


def test_watch_list_accepts_optional_source_ids(tmp_path):
    venue = {"name": "TIP", "kind": "journal", "group": "Journals", "issn": ["1057-7149", "1941-0042"], "openalex_source": "S4210173141", "sources": ["openalex", "crossref"]}

    assert feed.load_watchlist(write_list(tmp_path, [venue])) == [venue]


def test_the_lawful_sources_are_fixed_in_code():
    assert feed.SOURCES == ("openalex", "crossref", "openreview")


# --- Lines --------------------------------------------------------------------


@pytest.mark.parametrize("source", ["openalex", "crossref", "openreview"])
def test_each_lawful_source_is_accepted(source):
    papers, invalid = feed.parse_output(line(source=source))

    assert invalid == 0 and papers[0].record["source"] == source


@pytest.mark.parametrize("source", ["scihub", "semantic", "arxiv", "", None, "OpenAlex"])
def test_any_other_source_is_refused(source):
    papers, invalid = feed.parse_output(line(source=source))

    assert (papers, invalid) == ([], 1)


def test_published_record_has_the_shape_and_no_abstract():
    [paper], _ = feed.parse_output(line(oa_url="https://example.edu/paper.pdf"))

    assert paper.record == {
        "id": "doi:10.1109/tcsvt.2026.1234567",
        "source": "openalex",
        "title": "Stereo Video from Monocular Clips",
        "authors": ["Ada Lovelace", "Alan Turing"],
        "venue": "IEEE TCSVT",
        "published": "2026-11-05",
        "doi": "10.1109/tcsvt.2026.1234567",
        "oa_url": "https://example.edu/paper.pdf",
        "url": "https://doi.org/10.1109/TCSVT.2026.1234567",
        "categories": [],
        "has_abstract": True,
    }
    assert set(paper.record) == shapes.FeedRecord.__required_keys__
    assert paper.abstract == "We convert monocular clips to stereo."
    assert not is_arxiv(paper.record)


@pytest.mark.parametrize(
    "ids, expected",
    [
        ({"arxiv_id": "arXiv:2611.01234v2", "doi": "10.1/x", "openreview_id": "abc"}, "2611.01234"),
        ({"doi": "https://doi.org/10.1145/ABC.1", "openreview_id": "abc"}, "doi:10.1145/abc.1"),
        ({"doi": None, "openreview_id": "aBc_12"}, "openreview:aBc_12"),
    ],
)
def test_id_is_the_arxiv_id_then_the_doi_then_the_openreview_forum(ids, expected):
    [paper], _ = feed.parse_output(line(**{"arxiv_id": None, "doi": None, "openreview_id": None, **ids}))

    assert paper.record["id"] == expected


def test_invalid_lines_are_dropped_and_counted():
    lines = [
        line(),
        "not json",
        "[1, 2]",
        line(title=" "),
        line(published="5 Nov 2026"),
        line(authors="Ada Lovelace"),
        line(doi=None, arxiv_id=None, openreview_id=None),
        line(url="javascript:alert(1)"),
        line(oa_url="ftp://example.org/x.pdf"),
        line(abstract=12),
        "",
    ]

    papers, invalid = feed.parse_output("\n".join(lines))

    assert len(papers) == 1 and invalid == 9


def test_an_empty_abstract_counts_as_none():
    [paper], _ = feed.parse_output(line(abstract="   "))

    assert paper.abstract is None and paper.record["has_abstract"] is False


# --- Dedupe -------------------------------------------------------------------


def arxiv(paper_id, title, first="Ada Lovelace"):
    return {"id": paper_id, "categories": ["cs.CV"], "title": title, "authors": [first], "summary": "x"}


def parsed(**overrides):
    return feed.parse_output(line(**overrides))[0][0]


def test_a_feed_paper_matching_by_arxiv_id_is_not_added():
    existing = [arxiv("2611.01234", "Something else entirely")]

    kept, dropped = dedupe.fresh(existing, [parsed(arxiv_id="2611.01234v1")])

    assert (kept, dropped) == ([], 1)


def test_a_feed_paper_matching_by_doi_is_not_added():
    existing = [{**parsed().record, "title": "Old title", "id": "doi:10.1109/tcsvt.2026.1234567"}]

    kept, dropped = dedupe.fresh(existing, [parsed(doi="https://doi.org/10.1109/TCSVT.2026.1234567", source="crossref")])

    assert (kept, dropped) == ([], 1)


def test_a_journal_version_of_an_arxiv_paper_matches_by_title_and_first_author():
    existing = [arxiv("2605.00001", "Stereo video from monocular clips.", first="A. Lovelace")]

    kept, dropped = dedupe.fresh(existing, [parsed(title="Stereo Video from Monocular Clips", authors=["Ada Lovelace"])])

    assert (kept, dropped) == ([], 1)


def test_the_same_title_by_another_first_author_is_kept():
    existing = [arxiv("2605.00001", "Stereo Video from Monocular Clips", first="Grace Hopper")]

    kept, dropped = dedupe.fresh(existing, [parsed()])

    assert (len(kept), dropped) == (1, 0)


def test_the_batch_is_deduplicated_and_keeps_the_most_complete_copy():
    """OpenAlex and OpenReview list the same paper; the copy kept gains the other's abstract and OA link."""
    first = parsed(source="openalex", abstract=None, oa_url=None)
    second = parsed(source="openreview", doi=None, openreview_id="xyz", oa_url="https://openreview.net/pdf?id=xyz")

    kept, dropped = dedupe.fresh([], [first, second])

    assert dropped == 1 and len(kept) == 1
    assert kept[0].record["id"] == "doi:10.1109/tcsvt.2026.1234567"
    assert kept[0].record["oa_url"] == "https://openreview.net/pdf?id=xyz"
    assert kept[0].abstract == "We convert monocular clips to stereo."
    assert kept[0].record["has_abstract"] is True


@pytest.mark.parametrize(
    "author, family",
    [("Ada Lovelace", "lovelace"), ("Lovelace, Ada", "lovelace"), ("José Núñez", "nunez"), ("", ""), ("Ludwig van Beethoven", "beethoven")],
)
def test_family_name(author, family):
    assert dedupe.family_name(author) == family


def similar(a, b):
    return SequenceMatcher(None, dedupe.normalise_title(a), dedupe.normalise_title(b)).ratio()


def test_no_two_published_records_have_titles_more_than_ninety_percent_alike():
    """R2's acceptance on a sample shaped like Phase 0's: arXiv papers, their journal versions, and one paper from two sources."""
    existing = [
        arxiv("2605.00001", "Stereo Video from Monocular Clips"),
        arxiv("2605.00002", "Continual Learning without Forgetting: A Survey", first="Grace Hopper"),
        arxiv("2605.00003", "Weakly-Supervised Depth from Defocus", first="Alan Turing"),
    ]
    batch = [
        parsed(title="Stereo video from monocular clips"),
        parsed(title="Continual learning without forgetting - a survey", authors=["G. Hopper"], doi="10.1/a"),
        parsed(title="Weakly Supervised Depth From Defocus.", authors=["Alan M. Turing"], doi="10.1/b"),
        parsed(title="Weakly supervised depth from defocus", authors=["Alan Turing"], doi=None, openreview_id="q", source="openreview"),
        parsed(title="Light Field Saliency in the Wild", authors=["Edsger Dijkstra"], doi="10.1/c"),
        parsed(title="Light Field Saliency in the Wild", authors=["Edsger Dijkstra"], doi="10.1/c", source="crossref"),
        parsed(title="Binocular Rivalry in Natural Viewing", authors=["Barbara Liskov"], doi="10.1/d", venue="Journal of Vision"),
    ]

    kept, dropped = dedupe.fresh(existing, batch)

    published = existing + [p.record for p in kept]
    assert [p.record["title"] for p in kept] == ["Light Field Saliency in the Wild", "Binocular Rivalry in Natural Viewing"]
    assert dropped == 5
    for a, b in combinations(published, 2):
        assert similar(a["title"], b["title"]) <= 0.9, (a["title"], b["title"])
