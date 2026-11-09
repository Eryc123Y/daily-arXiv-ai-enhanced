import subprocess
from pathlib import Path

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


def test_crawl_runs_the_spider_like_the_workflow(tmp_path, scrapy):
    papers = localcrawl.crawl(tmp_path, "alice/my-arxiv")

    assert [p["id"] for p in papers] == ["A", "B"]
    [(cmd, kwargs)] = scrapy["calls"]
    assert cmd[:5] == ["uv", "run", "scrapy", "crawl", "arxiv"]
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
