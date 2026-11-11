"""Watch list v2: the venues Eric chose on 2026-11-12, their source fields, and topic-only venues.

A venue with `match: "topics"` contributes only papers whose title or abstract
matches one of the interest keywords (summaries/interests.py, the page's own
matching). The filter runs before dedupe, the burst cap and summaries.
"""

import json

import pytest

from summaries import feed
from summaries.interests import load_topics

# --- The watch list as chosen ------------------------------------------------------

TOPIC_ONLY = {
    # v1's large conferences: thousands of papers a year, most already on arXiv (ACM MM alone sent 871 in four weeks).
    "CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "ICLR", "AAAI", "IJCAI", "ACM MM",
    "ACL", "EMNLP", "NAACL", "EACL", "COLM",
    "AAMAS", "JAIR", "Artificial Intelligence (Elsevier)",
    "AISTATS", "UAI", "Annals of Statistics", "Machine Learning (Springer)", "IEEE TIT",
    "ICALP",
    "Cognitive Science",
    "Nature Machine Intelligence", "Neural Networks", "IEEE TNNLS",
    "IEEE TMM", "Vision Research",
    "PLOS Computational Biology",
}

TOP = {
    # Before watch list v2 every venue counted as top; they stay top.
    "CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "ICLR", "AAAI", "IJCAI", "ACM MM",
    "ACM TOG", "IEEE TVCG", "Computer Graphics Forum", "IEEE TPAMI", "IJCV", "IEEE TIP", "IEEE TCSVT",
    "JMLR", "TMLR", "Journal of Vision",
    # Flagships of the new areas.
    "ACL", "EMNLP", "NAACL", "TACL", "Computational Linguistics", "COLT", "LICS", "ICALP", "AAMAS",
    "JAIR", "Artificial Intelligence (Elsevier)", "Neural Computation", "Nature Machine Intelligence", "IEEE TIT",
}

SOURCE_FIELDS = {
    "ACL": {"acl_anthology": "acl"},
    "EMNLP": {"acl_anthology": "emnlp"},
    "NAACL": {"acl_anthology": "naacl"},
    "EACL": {"acl_anthology": "eacl"},
    "TACL": {"acl_anthology": "tacl", "openalex_source": "S2729999759", "issn": ["2307-387X"]},
    "Computational Linguistics": {"acl_anthology": "cl", "openalex_source": "S155526855", "issn": ["0891-2017", "1530-9312"]},
    "CoNLL": {"acl_anthology": "conll", "openalex_source": "S4306418031"},
    "Mathematics of Language": {"acl_anthology": "mol"},
    "COLM": {"openreview": "colmweb.org/COLM/{year}/Conference"},
    "RLC": {"openreview": "rl-conference.cc/RLC/{year}/Conference"},
    "COLT": {"pmlr": "COLT"},
    "ALT": {"pmlr": "ALT"},
    "AISTATS": {"pmlr": "AISTATS"},
    "UAI": {"pmlr": "UAI"},
    "CoLLAs": {"pmlr": "CoLLAs"},
    "ITP": {"doi_prefix": "10.4230/LIPIcs.ITP"},
    "ICALP": {"doi_prefix": "10.4230/LIPIcs.ICALP"},
    "AAMAS": {"openalex_source": "S4306417597"},
    "LICS": {"openalex_source": "S4210192682", "issn": ["1043-6871", "2575-5528"]},
    "TMLR": {"openreview": "TMLR", "issn": ["2835-8856"]},
    "JMLR": {"jmlr": True, "issn": ["1532-4435", "1533-7928"]},
}

NOT_ADDED = {"Findings of ACL", "COLING", "WMT", "LREC", "ICIP", "ACM TOMM", "Displays", "Journal of the SID", "IJAIED", "Interspeech"}


@pytest.fixture(scope="module")
def venues():
    return {v["name"]: v for v in feed.load_watchlist()}


def test_the_watch_list_holds_the_chosen_venues_once(venues):
    assert len(venues) == 63 == len(feed.load_watchlist())
    assert TOPIC_ONLY <= set(venues) and TOP <= set(venues)
    assert not NOT_ADDED & set(venues)


def test_only_the_large_venues_are_topic_only(venues):
    assert {name for name, v in venues.items() if v.get("match") == "topics"} == TOPIC_ONLY
    assert all(v.get("match", "all") in ("all", "topics") for v in venues.values())


def test_only_flagship_venues_are_top(venues):
    assert {name for name, v in venues.items() if v.get("top") is True} == TOP


@pytest.mark.parametrize("name", sorted(SOURCE_FIELDS))
def test_each_venue_names_its_sources(venues, name):
    venue = venues[name]
    for field, value in SOURCE_FIELDS[name].items():
        assert venue[field] == value, (name, field)


def test_every_venue_can_be_found_by_some_source(venues):
    fields = ("openalex_source", "issn", "openreview_venues", "jmlr", "acl_anthology", "pmlr", "doi_prefix", "openreview")
    assert [name for name, v in venues.items() if not any(v.get(f) for f in fields) and name != "ECCV"] == []


# --- Checking a watch list ----------------------------------------------------------


def write_list(tmp_path, venues):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"venues": venues}))
    return path


BASE = {"name": "ACL", "kind": "conference", "group": "NLP and linguistics", "area": "NLP and linguistics"}


def test_fields_unknown_here_pass_through_untouched(tmp_path):
    """LitScout reads the same file; a field it adds later must not stop the feed."""
    venue = {**BASE, "acl_anthology": "acl", "dblp_stream": "conf/acl", "notes": {"any": ["shape"]}}

    assert feed.load_watchlist(write_list(tmp_path, [venue])) == [venue]


def test_the_new_source_fields_and_flags_are_accepted(tmp_path):
    """Field names and values as agreed with LitScout's watch command on 2026-11-12."""
    venue = {**BASE, "jmlr": True, "acl_anthology": "acl", "pmlr": "COLT", "doi_prefix": "10.4230/LIPIcs.ITP",
             "openreview": "TMLR", "match": "topics", "top": True}
    several = {**BASE, "name": "COLM", "openreview": ["colmweb.org/COLM/{year}/Conference", "colmweb.org/COLM/2025/Conference"]}

    assert feed.load_watchlist(write_list(tmp_path, [venue, several])) == [venue, several]


@pytest.mark.parametrize(
    "change",
    [
        {"match": "some"},
        {"match": True},
        {"top": "yes"},
        {"top": 1},
        {"acl_anthology": ""},
        {"pmlr": ["colt"]},
        {"doi_prefix": 10.4230},
        {"openreview": "  "},
        {"openreview": []},
        {"openreview": ["TMLR", ""]},
        {"jmlr": "yes"},
    ],
)
def test_a_known_field_of_the_wrong_kind_is_refused(tmp_path, change):
    with pytest.raises(feed.FeedError, match=next(iter(change))):
        feed.load_watchlist(write_list(tmp_path, [{**BASE, **change}]))


@pytest.mark.parametrize("source", ["acl-anthology", "pmlr", "datacite", "jmlr"])
def test_the_new_line_sources_are_accepted(source):
    line = {
        "source": source, "title": "A paper", "authors": ["Ada Lovelace"], "venue": "ACL", "published": "2026-11-05",
        "doi": None, "arxiv_id": None, "openreview_id": None, "abstract": None, "oa_url": None,
        "url": "https://aclanthology.org/2026.acl-long.1/",
    }
    papers, invalid = feed.parse_output(json.dumps({**line, "doi": "10.18653/v1/2026.acl-long.1"}))

    assert invalid == 0 and papers[0].record["source"] == source


def test_a_paper_without_doi_arxiv_or_openreview_id_is_kept_under_its_url():
    """PMLR and JMLR papers have no DOI; without this they would all be dropped as invalid lines."""
    line = {
        "source": "pmlr", "title": "Online learning", "authors": ["Ada Lovelace"], "venue": "COLT", "published": "2026-07-01",
        "doi": None, "arxiv_id": None, "openreview_id": None, "abstract": None, "oa_url": None,
        "url": "https://proceedings.mlr.press/v337/alfarra26a.html",
    }
    [paper], invalid = feed.parse_output(json.dumps(line))

    assert invalid == 0 and paper.record["id"] == "url:https://proceedings.mlr.press/v337/alfarra26a.html"


# --- The topic filter ------------------------------------------------------------------

TOPICS = [
    {"name": "Formal", "keywords": ["regular language", "Lean"]},
    {"name": "RL", "keywords": ["reinforcement learning"]},
]
WATCH = [
    {**BASE, "match": "topics"},
    {"name": "EMNLP", "kind": "conference", "group": "x", "match": "topics"},
    {"name": "TACL", "kind": "journal", "group": "x", "match": "all"},
    {"name": "CoNLL", "kind": "conference", "group": "x"},
]


def paper(venue, title, abstract=None):
    line = {
        "source": "openalex", "title": title, "authors": ["Ada Lovelace"], "venue": venue, "published": "2026-11-05",
        "doi": f"10.1/{abs(hash((venue, title)))}", "arxiv_id": None, "openreview_id": None, "abstract": abstract,
        "oa_url": None, "url": "https://example.org/paper",
    }
    [parsed], _ = feed.parse_output(json.dumps(line))
    return parsed


def test_a_topic_only_venue_keeps_papers_that_match_a_keyword_in_title_or_abstract():
    on_title = paper("ACL", "Transformers recognise regular languages")
    on_abstract = paper("ACL", "A study of agents", "We use reinforcement learning to train them.")
    off = paper("ACL", "A sentiment dataset", "We annotate tweets.")

    kept, dropped = feed.on_topic([on_title, off, on_abstract], WATCH, TOPICS)

    assert kept == [on_title, on_abstract]
    assert dropped == {"ACL": 1}


def test_a_title_alone_is_enough_when_the_abstract_is_missing():
    """Most Neural Networks records have no abstract; they are matched on the title."""
    kept, dropped = feed.on_topic([paper("EMNLP", "Reinforcement Learning for Parsing")], WATCH, TOPICS)

    assert len(kept) == 1 and dropped == {}


def test_venues_matching_all_unknown_venues_and_other_venues_keep_everything():
    papers = [paper("TACL", "A sentiment dataset"), paper("CoNLL", "Tweets"), paper("Unlisted", "Anything")]

    kept, dropped = feed.on_topic(papers, WATCH, TOPICS)

    assert kept == papers and dropped == {}


def test_drops_are_counted_per_venue():
    papers = [paper("ACL", "Tweets"), paper("EMNLP", "Emoji"), paper("ACL", "Memes"), paper("ACL", "A Lean proof of it")]

    kept, dropped = feed.on_topic(papers, WATCH, TOPICS)

    assert [p.record["title"] for p in kept] == ["A Lean proof of it"]
    assert dropped == {"ACL": 2, "EMNLP": 1}


def test_the_ordinary_word_lean_does_not_let_a_paper_through():
    kept, dropped = feed.on_topic([paper("ACL", "A lean architecture for parsing")], WATCH, TOPICS)

    assert kept == [] and dropped == {"ACL": 1}


def test_the_filter_reads_the_shipped_topics_by_default():
    kept, _ = feed.on_topic([paper("ACL", "Emergent communication in referential games")], WATCH)

    assert len(kept) == 1
    assert load_topics()  # the same topics the daily report and the page use
