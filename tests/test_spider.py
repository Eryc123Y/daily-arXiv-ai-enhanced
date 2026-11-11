from pathlib import Path

from daily_arxiv.spiders.arxiv import ArxivSpider
from scrapy.http import HtmlResponse, Request

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


def code_url_of(*hrefs):
    links = "".join(f'<a href="{h}">this https URL</a> ' for h in hrefs)
    html = f'<dl><dd><p class="mathjax">Abstract {links}</p></dd></dl>'
    response = HtmlResponse(url=URL, body=html.encode(), encoding="utf-8", request=Request(URL))
    return ArxivSpider._code_url(response.css("dd"))


def test_gitlab_codeberg_and_anonymous_review_repos_count_as_code():
    assert code_url_of("https://gitlab.com/group/tool/-/tree/main") == "https://gitlab.com/group/tool"
    assert code_url_of("https://codeberg.org/me/proj.git") == "https://codeberg.org/me/proj"
    assert code_url_of("https://anonymous.4open.science/r/Model-1A2B/") == "https://anonymous.4open.science/r/Model-1A2B"


def test_a_repo_link_wins_over_a_project_page():
    assert code_url_of("https://me.github.io/proj", "https://github.com/me/proj") == "https://github.com/me/proj"
    assert code_url_of("https://me.gitlab.io/proj/") == "https://me.gitlab.io/proj/"
    assert code_url_of("https://example.com/proj") is None


RECENT_FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_recent_cs_CV.html"
RECENT_URL = "https://arxiv.org/list/cs.CV/recent?skip=0&show=2000"


def parse_recent(body=None, url=RECENT_URL):
    response = HtmlResponse(url=url, body=body or RECENT_FIXTURE.read_bytes(), encoding="utf-8", request=Request(url))
    return list(ArxivSpider(categories="cs.CV", listing="recent").parse(response))


def test_recent_listing_mode_reads_the_last_announcements(monkeypatch):
    monkeypatch.setenv("CATEGORIES", "cs.CV, stat.ML")
    urls = sorted(ArxivSpider(listing="recent").start_urls)
    assert urls == [
        "https://arxiv.org/list/cs.CV/recent?skip=0&show=2000",
        "https://arxiv.org/list/stat.ML/recent?skip=0&show=2000",
    ]


def test_recent_listing_tags_each_paper_with_its_announcement_day():
    """Fixture: Monday has a new paper, a same-month cross-list and a late cross-list; Friday one paper."""
    items = parse_recent()
    assert [(i["id"], i["announced"]) for i in items] == [
        ("2611.00001", "2026-11-09"),
        ("2611.00002", "2026-11-09"),
        ("2611.00004", "2026-11-06"),
    ]
    friday = items[-1]
    assert friday["title"] == "A Friday Paper"
    assert friday["authors"] == ["Edsger Dijkstra"]
    assert friday["categories"] == ["cs.CV"]
    assert friday["code_url"] == "https://github.com/ed/friday"
    assert items[1]["categories"] == ["cs.LG", "cs.CV"]


def test_recent_listing_follows_the_next_page_when_there_are_more_entries():
    body = RECENT_FIXTURE.read_text().replace("Total of 4 entries", "Total of 2500 entries").encode()
    results = parse_recent(body)
    requests = [r for r in results if isinstance(r, Request)]
    assert [r.url for r in requests] == ["https://arxiv.org/list/cs.CV/recent?skip=2000&show=2000"]
    assert sum(1 for r in results if isinstance(r, dict)) == 3


def test_recent_listing_continued_page_keeps_the_day_heading():
    body = RECENT_FIXTURE.read_text().replace("Fri, 6 Nov 2026 (showing 1 of 1 entries )", "Fri, 6 Nov 2026 (continued, showing 1 of 1 entries )")
    items = parse_recent(body.encode(), url="https://arxiv.org/list/cs.CV/recent?skip=2000&show=2000")
    assert items[-1]["announced"] == "2026-11-06"
