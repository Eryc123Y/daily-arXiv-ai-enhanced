"""Where the reading page lives: summaries/sites.json for this repository, GitHub Pages for forks."""

import json

import pytest

from summaries import digest, github

LITSCOUT = "https://litscout.turing2234.com/"


def test_this_repository_uses_its_own_domain():
    assert github.site_url("Eryc123Y/daily-arXiv-ai-enhanced") == LITSCOUT
    assert github.site_url("eryc123y/Daily-arXiv-AI-enhanced") == LITSCOUT


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("alice/my-arxiv", "https://alice.github.io/my-arxiv/"),
        ("Alice/My-Arxiv", "https://alice.github.io/My-Arxiv/"),
        ("alice/alice.github.io", "https://alice.github.io/"),
    ],
)
def test_a_fork_without_an_entry_uses_github_pages(slug, expected):
    assert github.site_url(slug) == expected


def test_an_entry_in_the_sites_file_wins_and_ends_with_a_slash(tmp_path):
    sites = tmp_path / "sites.json"
    sites.write_text(json.dumps({"addresses": {"Alice/My-Arxiv": "https://papers.example.org"}}), encoding="utf-8")
    assert github.site_url("alice/my-arxiv", sites) == "https://papers.example.org/"
    assert github.site_url("bob/my-arxiv", sites) == "https://bob.github.io/my-arxiv/"


def test_a_missing_sites_file_means_github_pages(tmp_path):
    assert github.site_url("alice/my-arxiv", tmp_path / "none.json") == "https://alice.github.io/my-arxiv/"


def test_the_sites_file_only_holds_https_addresses():
    addresses = json.loads(github.SITES.read_text(encoding="utf-8"))["addresses"]
    assert addresses == {"Eryc123Y/daily-arXiv-ai-enhanced": LITSCOUT}
    assert all(url.startswith("https://") and url.endswith("/") for url in addresses.values())


def test_reports_link_to_the_configured_address(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_REPO", "Eryc123Y/daily-arXiv-ai-enhanced")
    assert digest.site_url(tmp_path) == LITSCOUT
    monkeypatch.setenv("DATA_REPO", "alice/my-arxiv")
    assert digest.site_url(tmp_path) == "https://alice.github.io/my-arxiv/"
