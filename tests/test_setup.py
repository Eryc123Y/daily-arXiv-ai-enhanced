import json
import subprocess

import pytest
from conftest import git, seed_data_branch

from summaries import cli
from summaries.cli import main, parse_repo_slug, repo_slug
from summaries.databranch import BOT_IDENTITY, Identity, resolve_identity
from summaries.records import dump_jsonl

DAY = "2026-10-30"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/alice/my-arxiv.git",
        "https://github.com/alice/my-arxiv",
        "git@github.com:alice/my-arxiv.git",
        "ssh://git@github.com/alice/my-arxiv.git",
        "https://x-access-token:secret@github.com/alice/my-arxiv",
    ],
)
def test_repo_slug_is_read_from_the_origin_url(url):
    assert parse_repo_slug(url) == "alice/my-arxiv"


def test_repo_slug_prefers_explicit_settings(remote_and_clone, monkeypatch):
    _, clone = remote_and_clone
    git(clone, "remote", "set-url", "origin", "git@github.com:alice/my-arxiv.git")
    monkeypatch.delenv("DATA_REPO", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert repo_slug(clone) == "alice/my-arxiv"
    monkeypatch.setenv("GITHUB_REPOSITORY", "bob/other")
    assert repo_slug(clone) == "bob/other"
    monkeypatch.setenv("DATA_REPO", "carol/third")
    assert repo_slug(clone) == "carol/third"


def test_commit_identity_comes_from_settings_then_actions_then_git_config(remote_and_clone):
    _, clone = remote_and_clone
    named = {"COMMIT_NAME": "Alice", "COMMIT_EMAIL": "1+alice@users.noreply.github.com"}
    assert resolve_identity(clone, named) == Identity("Alice", "1+alice@users.noreply.github.com")
    assert resolve_identity(clone, {"GITHUB_ACTIONS": "true"}) == BOT_IDENTITY
    git(clone, "config", "user.name", "Local Person")
    git(clone, "config", "user.email", "local@example.invalid")
    assert resolve_identity(clone, {}) == Identity("Local Person", "local@example.invalid")


def test_ingest_publishes_the_site_settings(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    crawl = tmp_path / "crawl.jsonl"
    crawl.write_text(dump_jsonl([{"id": "1", "categories": ["cs.CV"], "title": "T", "summary": "S", "authors": []}]))
    monkeypatch.setenv("CATEGORIES", "cs.CV, cs.RO ,stat.ML")
    monkeypatch.setenv("LANGUAGE", "English")

    main(["--repo", str(clone), "ingest", "--date", DAY, "--input", str(crawl)])

    site = json.loads(git(remote, "show", "data:assets/site.json"))
    assert site == {"categories": ["cs.CV", "cs.RO", "stat.ML"], "language": "English"}


def fake_gh(calls, fail=()):
    def gh(*args):
        calls.append(args)
        if any(args[: len(f)] == f for f in fail):
            raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 409: already exists")
        return ""

    return gh


def test_setup_configures_a_fork_in_one_command(remote_and_clone, monkeypatch, capsys):
    _, clone = remote_and_clone
    git(clone, "remote", "set-url", "origin", "https://github.com/alice/my-arxiv.git")
    monkeypatch.delenv("DATA_REPO", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    calls = []
    monkeypatch.setattr(cli, "gh", fake_gh(calls, fail=[("api", "-X", "POST")]))

    code = main(["--repo", str(clone), "setup", "--categories", "cs.CV, cs.LG", "--provider", "gemini", "--model", "g-1", "--run"])

    out = capsys.readouterr().out
    assert code == 0
    assert ("variable", "set", "CATEGORIES", "-R", "alice/my-arxiv", "--body", "cs.CV, cs.LG") in calls
    assert ("variable", "set", "SUMMARY_MODE", "-R", "alice/my-arxiv", "--body", "claude-code") in calls
    assert ("variable", "set", "SUMMARY_PROVIDER", "-R", "alice/my-arxiv", "--body", "gemini") in calls
    assert ("workflow", "run", "run.yml", "-R", "alice/my-arxiv") in calls
    assert not any(c[0] == "secret" for c in calls), "setup never handles keys"
    assert "https://alice.github.io/my-arxiv/" in out
    assert "already" in out  # Pages was enabled before
    assert "gh secret set GEMINI_API_KEY" in out
