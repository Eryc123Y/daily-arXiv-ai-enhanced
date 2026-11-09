import io
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

import pytest

from summaries import github, localcrawl
from summaries.records import dump_jsonl


def paper(paper_id):
    return {"id": paper_id, "categories": ["cs.CV"], "title": f"T{paper_id}", "authors": ["A"], "summary": f"S{paper_id}"}


def test_categories_come_from_the_environment_first(monkeypatch):
    monkeypatch.setenv("CATEGORIES", "cs.RO")
    monkeypatch.setattr(github, "gh", lambda *args: pytest.fail("gh should not be asked"))

    assert localcrawl.categories("alice/my-arxiv") == "cs.RO"


def test_categories_come_from_the_repository_variable_like_the_workflow(monkeypatch):
    monkeypatch.delenv("CATEGORIES", raising=False)
    calls = []

    def gh(*args):
        calls.append(args)
        return "cs.CV, cs.GR\n"

    monkeypatch.setattr(github, "gh", gh)

    assert localcrawl.categories("alice/my-arxiv") == "cs.CV, cs.GR"
    assert calls == [("variable", "get", "CATEGORIES", "-R", "alice/my-arxiv")]


def test_categories_fall_back_to_the_workflow_default(monkeypatch):
    monkeypatch.delenv("CATEGORIES", raising=False)

    def gh(*args):
        raise subprocess.CalledProcessError(1, ["gh"], stderr="variable CATEGORIES was not found")

    monkeypatch.setattr(github, "gh", gh)

    assert localcrawl.categories("alice/my-arxiv") == localcrawl.DEFAULT_CATEGORIES


@pytest.fixture
def scrapy(monkeypatch):
    """Stand-in for `uv run scrapy crawl`: records the call and writes `rows` to the -o file."""
    monkeypatch.setattr(localcrawl, "categories", lambda slug: "cs.CV, cs.GR")
    state = {"calls": [], "rows": [paper("A"), paper("B")], "error": None}

    def run(cmd, **kwargs):
        state["calls"].append((cmd, kwargs))
        if state["error"]:
            raise state["error"]
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text(dump_jsonl(state["rows"]) if state["rows"] else "", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(localcrawl.subprocess, "run", run)
    return state


def test_crawl_runs_the_spider_on_the_new_listing(tmp_path, scrapy):
    papers = localcrawl.crawl(tmp_path, "alice/my-arxiv")

    assert [p["id"] for p in papers] == ["A", "B"]
    [(cmd, kwargs)] = scrapy["calls"]
    assert cmd[:5] == ["uv", "run", "scrapy", "crawl", "arxiv"]
    assert "listing=recent" not in cmd
    assert Path(kwargs["cwd"]) == tmp_path / "daily_arxiv"
    assert kwargs["env"]["CATEGORIES"] == "cs.CV, cs.GR"
    assert kwargs["check"] is True and kwargs["timeout"] > 0


def test_crawl_with_no_papers_is_an_error(tmp_path, scrapy):
    scrapy["rows"] = []

    with pytest.raises(localcrawl.CrawlError, match="no papers"):
        localcrawl.crawl(tmp_path, "alice/my-arxiv")


def test_crawl_that_exits_with_an_error_says_why(tmp_path, scrapy):
    scrapy["error"] = subprocess.CalledProcessError(1, ["uv"], stderr="line one\nDNS lookup failed for arxiv.org\n")

    with pytest.raises(localcrawl.CrawlError, match="DNS lookup failed"):
        localcrawl.crawl(tmp_path, "alice/my-arxiv")


def atom(entries):
    body = "".join(
        f"<entry><id>http://arxiv.org/abs/{i}v2</id><title>t</title><summary>\n  Abstract of {i}\n  over two lines. </summary></entry>"
        for i in entries
    )
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">{body}</feed>'.encode()


@pytest.fixture
def arxiv_api(monkeypatch):
    """Stand-in for the arXiv API: answers id_list queries, leaving out `missing` ids."""
    state = {"urls": [], "missing": set(), "error": None, "sleeps": []}

    def urlopen(request, timeout=None):
        url = request.full_url
        state["urls"].append(url)
        if state["error"]:
            raise state["error"]
        ids = parse_qs(urlparse(url).query)["id_list"][0].split(",")
        return io.BytesIO(atom([i for i in ids if i not in state["missing"]]))

    monkeypatch.setattr(localcrawl, "urlopen", urlopen)
    monkeypatch.setattr(localcrawl.time, "sleep", lambda seconds: state["sleeps"].append(seconds))
    return state


def test_recent_returns_the_requested_days_with_abstracts_from_the_api(tmp_path, scrapy, arxiv_api):
    scrapy["rows"] = [
        {**paper("2611.00001"), "summary": "", "announced": "2026-11-09"},
        {**paper("2611.00004"), "summary": "", "announced": "2026-11-06"},
        {**paper("2611.00005"), "summary": "", "announced": "2026-11-06"},
        {**paper("2611.00006"), "summary": "", "announced": "2026-11-05"},
    ]
    arxiv_api["missing"] = {"2611.00005"}

    days = localcrawl.recent(tmp_path, "alice/my-arxiv", ["2026-11-06", "2026-11-05"]).days

    [(cmd, _)] = scrapy["calls"]
    assert "listing=recent" in cmd
    assert sorted(days) == ["2026-11-05", "2026-11-06"]
    assert [p["id"] for p in days["2026-11-06"]] == ["2611.00004"]  # no abstract, left out
    assert days["2026-11-06"][0]["summary"] == "Abstract of 2611.00004 over two lines."
    assert "announced" not in days["2026-11-06"][0]
    [url] = arxiv_api["urls"]
    assert url.startswith("https://export.arxiv.org/api/query?")
    assert "2611.00001" not in url  # today's paper was not asked for


def test_recent_lists_the_days_the_listing_covers(tmp_path, scrapy, arxiv_api):
    scrapy["rows"] = [{**paper("X"), "announced": d} for d in ("2026-11-09", "2026-11-03")]

    listing = localcrawl.recent(tmp_path, "alice/my-arxiv", [])

    assert listing.covered == ["2026-11-03", "2026-11-09"] and listing.days == {}
    assert arxiv_api["urls"] == []


def test_abstracts_are_fetched_in_batches_with_a_pause_between(arxiv_api):
    ids = [f"2611.{n:05d}" for n in range(150)]

    found = localcrawl.fetch_abstracts(ids)

    assert len(found) == 150 and len(arxiv_api["urls"]) == 2
    assert arxiv_api["sleeps"] == [localcrawl.API_PAUSE]


def test_an_unreachable_api_is_a_crawl_error(arxiv_api):
    arxiv_api["error"] = URLError("timed out")

    with pytest.raises(localcrawl.CrawlError, match="arXiv API"):
        localcrawl.fetch_abstracts(["2611.00001"])
