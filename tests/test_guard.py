"""The suite's guard: no test reaches the real repository's remote, GitHub or the network."""

import subprocess

import pytest
import requests

from conftest import REPO_ROOT, git


def test_remote_git_in_the_real_checkout_is_refused():
    with pytest.raises(RuntimeError, match="real repository"):
        subprocess.run(["git", "ls-remote", "--heads", "origin", "data"], cwd=REPO_ROOT, capture_output=True)
    with pytest.raises(RuntimeError, match="real repository"):
        subprocess.run(["git", "fetch", "origin"], cwd=REPO_ROOT / "summaries", capture_output=True)


def test_local_git_in_the_real_checkout_still_works():
    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.stdout.strip() == "true"


def test_remote_git_between_temporary_repositories_works(remote_and_clone):
    _, clone = remote_and_clone
    assert git(clone, "ls-remote", "--heads", "origin", "main")


def test_gh_is_refused():
    with pytest.raises(RuntimeError, match="gh"):
        subprocess.run(["gh", "run", "list"], capture_output=True)


def test_the_network_is_refused():
    with pytest.raises(RuntimeError, match="network"):
        requests.get("https://arxiv.org/list/cs.CV/new", timeout=5)
