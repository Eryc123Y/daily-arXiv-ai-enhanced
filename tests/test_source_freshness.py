"""Pure helpers of docs/measurements/source_freshness.py (no network)."""

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parent.parent / "docs" / "measurements" / "source_freshness.py"
spec = importlib.util.spec_from_file_location("source_freshness", PATH)
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)

TODAY = dt.date(2026, 11, 11)


def test_abstract_text_rebuilds_word_order():
    assert sf.abstract_text({"stereo": [1], "Deep": [0], "video": [2, 4], "and": [3]}) == "Deep stereo video and video"
    assert sf.abstract_text(None) == ""


def test_crossref_date_full_partial_and_missing():
    assert sf.crossref_date({"date-parts": [[2026, 11, 3]]}) == (dt.date(2026, 11, 3), True)
    assert sf.crossref_date({"date-parts": [[2026, 11]]}) == (dt.date(2026, 11, 1), False)
    assert sf.crossref_date({"date-parts": [[None]]}) == (None, False)
    assert sf.crossref_date(None) == (None, False)


def test_normalize_title_drops_markup_case_and_punctuation():
    assert sf.normalize_title("<i>Stereo</i>-Video:  Depth!") == "stereo video depth"
    assert sf.normalize_title(None) == ""


@pytest.mark.parametrize("text, expected", [
    ("https://arxiv.org/abs/2611.01234v2", "2611.01234"),
    ("https://arxiv.org/pdf/2510.9876", "2510.9876"),
    ("10.48550/arXiv.2611.01234", "2611.01234"),
    ("arXiv:2601.00001", "2601.00001"),
    ("https://doi.org/10.1109/tip.2026.1", None),
    (None, None),
])
def test_arxiv_id(text, expected):
    assert sf.arxiv_id(text) == expected


def test_date_flags():
    d = dt.date
    assert sf.date_flags(d(2026, 11, 2), d(2026, 11, 5), TODAY) == []
    assert sf.date_flags(None, d(2026, 11, 5), TODAY) == ["missing"]
    assert sf.date_flags(d(2026, 1, 1), d(2026, 11, 5), TODAY) == ["jan1"]
    assert sf.date_flags(d(2027, 2, 1), d(2026, 11, 5), TODAY) == ["future"]
    assert sf.date_flags(d(2026, 11, 8), d(2026, 11, 5), TODAY) == ["after_listing"]
    assert sf.date_flags(d(2026, 11, 1), d(2026, 11, 5), TODAY, exact=False) == ["partial"]


def test_delay_days():
    assert sf.delay_days(dt.date(2026, 11, 1), dt.date(2026, 11, 4)) == 3
    assert sf.delay_days(None, dt.date(2026, 11, 4)) is None


def test_quantile_interpolates():
    assert sf.quantile([], 0.5) is None
    assert sf.quantile([5, 1, 3], 0.5) == 3
    assert sf.quantile([0, 10], 0.9) == pytest.approx(9)


@pytest.mark.parametrize("median, papers, expected", [
    (0, 10, "daily"), (3, 10, "daily"), (3.5, 10, "weekly"), (40, 10, "weekly"), (None, 0, "not worth it"), (2, 0, "not worth it"),
])
def test_verdict(median, papers, expected):
    assert sf.verdict(median, papers) == expected


def test_share_and_pages():
    assert sf.share(1, 4) == "25%"
    assert sf.share(0, 0) == "-"
    assert sf.pages_needed(0) == 1
    assert sf.pages_needed(201) == 2


def test_openalex_record_finds_arxiv_oa_and_dates():
    work = {"id": "W1", "doi": "https://doi.org/10.1/X", "title": "T", "publication_date": "2026-11-01", "created_date": "2026-11-04",
            "abstract_inverted_index": {"a": [0]}, "open_access": {"oa_url": "https://x"},
            "locations": [{"landing_page_url": "https://arxiv.org/abs/2611.00001"}]}
    rec = sf.openalex_record(work, TODAY)
    assert (rec["doi"], rec["arxiv"], rec["oa"], rec["abstract"], rec["flags"]) == ("10.1/x", "2611.00001", True, "a", [])
    assert sf.delay_days(rec["published"], rec["listed"]) == 3


def test_crossref_record_prefers_online_date_and_reads_license():
    item = {"DOI": "10.1109/TIP.2026.1", "title": ["A <i>B</i>"], "created": {"date-parts": [[2026, 11, 5]]},
            "published-online": {"date-parts": [[2026, 11, 4]]}, "issued": {"date-parts": [[2027, 1]]},
            "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
            "relation": {"has-preprint": [{"id": "10.48550/arXiv.2601.00002"}]}, "abstract": "<jats:p>Hi</jats:p>"}
    rec = sf.crossref_record(item, TODAY)
    assert rec["published"] == dt.date(2026, 11, 4) and rec["flags"] == []
    assert (rec["oa"], rec["arxiv"], rec["abstract"]) == (True, "2601.00002", "Hi")


def test_lag_behind_doi_skips_unknown_dois():
    d = dt.date
    records = [{"doi": "10.1/a", "listed": d(2026, 11, 5)}, {"doi": "10.1/b", "listed": d(2026, 11, 5)}, {"doi": "", "listed": d(2026, 11, 5)}]
    assert sf.lag_behind_doi(records, {"10.1/a": d(2026, 11, 2)}) == [3]


def test_window_is_fourteen_days_inclusive():
    assert sf.first_day(TODAY) == dt.date(2026, 10, 29)
    assert sf.in_window(dt.date(2026, 10, 29), TODAY) and sf.in_window(TODAY, TODAY)
    assert not sf.in_window(dt.date(2026, 10, 28), TODAY) and not sf.in_window(None, TODAY)
