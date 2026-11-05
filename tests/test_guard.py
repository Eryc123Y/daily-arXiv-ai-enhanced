"""The suite's guard (conftest.py at the repository root): no test reaches GitHub, the network or the real remote."""

import socket
import subprocess
from pathlib import Path

import pytest
import requests

from conftest import git
from summaries import local_runner

REPO_ROOT = Path(__file__).resolve().parents[1]


def refused(result):
    return result.returncode != 0 and "not allowed" in result.stderr


def test_git_cannot_reach_the_real_remote_by_any_route(tmp_path):
    def run(argv, **kwargs):
        return subprocess.run(argv, capture_output=True, text=True, **kwargs)

    assert refused(run(["git", "ls-remote", "--heads", "origin", "data"], cwd=REPO_ROOT))
    assert refused(run(["git", "-C", str(REPO_ROOT), "fetch", "origin"], cwd=tmp_path))
    assert refused(run(["git", "remote", "update"], cwd=REPO_ROOT))
    git_dir = run(["git", "rev-parse", "--absolute-git-dir"], cwd=REPO_ROOT).stdout.strip()
    assert refused(run(["git", "fetch", "origin"], cwd=tmp_path, env={"GIT_DIR": git_dir, "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}))


def test_local_git_and_temporary_remotes_still_work(remote_and_clone):
    _, clone = remote_and_clone
    assert git(clone, "ls-remote", "--heads", "origin", "main")
    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.stdout.strip() == "true"


@pytest.mark.parametrize("call", [
    lambda: subprocess.run(["gh", "run", "list"], capture_output=True),
    lambda: subprocess.Popen(["gh", "api", "user"]),
    lambda: local_runner.run_command(["gh", "--version"]),
    lambda: subprocess.check_output("curl https://arxiv.org", shell=True),
])
def test_gh_and_downloaders_are_refused(call):
    with pytest.raises(RuntimeError, match="must not run"):
        call()


def test_the_network_is_refused_before_any_lookup():
    with pytest.raises(RuntimeError, match="network"):
        requests.get("https://arxiv.org/list/cs.CV/new", timeout=5)
    with pytest.raises(RuntimeError, match="resolve arxiv.org"):
        socket.create_connection(("arxiv.org", 443), timeout=5)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(RuntimeError, match="network"):
            sock.connect_ex(("192.0.2.1", 443))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        with pytest.raises(RuntimeError, match="network"):
            sock.sendto(b"x", ("192.0.2.1", 53))


def test_loopback_is_allowed():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=5):
            pass
