from pathlib import Path

from scrapy.http import HtmlResponse, Request

from daily_arxiv.spiders.arxiv import ArxivSpider

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_new_cs_CV.html"
URL = "https://arxiv.org/list/cs.CV/new?show=2000"


def parse_fixture():
    response = HtmlResponse(
        url=URL, body=FIXTURE.read_bytes(), encoding="utf-8", request=Request(URL)
    )
    return list(ArxivSpider(categories="cs.CV").parse(response))


def test_start_urls_cover_each_category_with_the_full_listing(monkeypatch):
    monkeypatch.setenv("CATEGORIES", "cs.CV, stat.ML")
    urls = sorted(ArxivSpider().start_urls)
    assert urls == [
        "https://arxiv.org/list/cs.CV/new?show=2000",
        "https://arxiv.org/list/stat.ML/new?show=2000",
    ]


def test_keeps_new_and_same_period_cross_lists_but_not_replacements():
    """Fixture: 3 new; cross-lists of a July paper and an October one; 1 replacement."""
    ids = [item["id"] for item in parse_fixture()]
    assert ids == ["2610.37784", "2610.37818", "2610.37874", "2610.37709"]


def test_cross_list_keeps_its_own_primary_category_first():
    cross = {item["id"]: item for item in parse_fixture()}["2610.37709"]
    assert cross["categories"][0] == "eess.IV"
    assert "cs.CV" in cross["categories"]


def test_github_link_from_abstract_or_comments_becomes_code_url():
    items = {item["id"]: item for item in parse_fixture()}
    assert items["2610.37874"]["code_url"] == "https://github.com/DarkJ0Y/PairCLIP-SWA"
    assert "code_url" not in items["2610.37784"]


def test_reads_full_metadata_from_the_listing():
    first = parse_fixture()[0]
    assert first["title"] == "Sparse tensor networks for individual tree diameter estimation in mixed forests"
    assert first["authors"][:2] == ["Clara Lößl", "Fabian Ewald Fassnacht"]
    assert first["categories"][0] == "cs.CV"
    assert first["summary"].startswith("Measurements of tree diameter at breast height (DBH)")
    assert "\n" not in first["summary"]
    assert first["abs"] == "https://arxiv.org/abs/2610.37784"
    assert first["pdf"] == "https://arxiv.org/pdf/2610.37784"
    assert "comment" in first


def test_cross_list_cutoff_uses_the_month_of_the_new_submissions():
    spider = ArxivSpider(categories="cs.CV")
    assert spider.is_late_cross_list("2607.03487", oldest_new_month="2610")
    assert not spider.is_late_cross_list("2610.37709", oldest_new_month="2610")
    assert not spider.is_late_cross_list("2610.37709", oldest_new_month=None)


def test_navigation_links_without_item_numbers_are_ignored():
    html = FIXTURE.read_text(encoding="utf-8").replace(
        '<li><a href="#item0">New submissions</a></li>',
        '<li><a href="#item0">New submissions</a></li><li><a href="/list/cs.CV/pastweek">Past week</a></li>',
    )
    response = HtmlResponse(url=URL, body=html.encode(), encoding="utf-8", request=Request(URL))
    assert len(list(ArxivSpider(categories="cs.CV").parse(response))) == 4


def test_cross_list_cutoff_falls_back_to_last_week_when_a_listing_has_no_new_papers():
    spider = ArxivSpider(categories="cs.CV")
    cutoff = spider.cross_list_cutoff([], today="2026-11-02")
    assert cutoff == "2610"
    assert spider.is_late_cross_list("2609.00001", cutoff)
    assert not spider.is_late_cross_list("2610.40001", cutoff)
