import ipaddress
import os
import socket
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REMOTE_GIT = {"fetch", "pull", "push", "ls-remote", "clone"}
_run = subprocess.run
_connect = socket.socket.connect

TEST_GIT = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "init.defaultBranch=main"]


def git(cwd, *args):
    result = subprocess.run(
        ["git", *TEST_GIT, *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def remote_and_clone(tmp_path):
    """A bare 'origin' with a main branch, and a fresh clone of it."""
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    clone = tmp_path / "clone"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "init", str(seed))
    (seed / "README.md").write_text("main\n")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "init")
    git(seed, "push", str(remote), "main")
    git(tmp_path, "clone", str(remote), str(clone))
    return remote, clone


def seed_data_branch(tmp_path, remote, files):
    """Push a data branch holding `files` ({path: text}) to `remote`."""
    work = tmp_path / "data-seed"
    git(tmp_path, "init", str(work))
    for path, text in files.items():
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    git(work, "add", ".")
    git(work, "commit", "-m", "seed data")
    git(work, "push", str(remote), "HEAD:refs/heads/data")
    return work


def _git_command(argv):
    """The git subcommand in `argv` (after -c/-C options), or None."""
    rest = list(argv[1:])
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in ("-c", "-C") else rest[1:]
    return rest[0] if rest else None


def _inside_repo(cwd):
    return Path(cwd or os.getcwd()).resolve().is_relative_to(REPO_ROOT)


def _guarded_run(args, *rest, **kwargs):
    argv = [str(a) for a in args] if isinstance(args, (list, tuple)) else str(args).split()
    program = Path(argv[0]).name if argv else ""
    if program == "gh":
        raise RuntimeError(f"tests must not call gh: {argv}; stub cli.gh instead")
    if program == "git" and _git_command(argv) in REMOTE_GIT and _inside_repo(kwargs.get("cwd")):
        raise RuntimeError(f"tests must not reach the real repository's remote: {argv}; pass --repo with a temporary clone")
    return _run(args, *rest, **kwargs)


def _is_local(address):
    if not isinstance(address, tuple):
        return True  # a Unix socket path
    host = address[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_connect(self, address):
    if not _is_local(address):
        raise RuntimeError(f"tests must not use the network: connect to {address}; stub the request instead")
    return _connect(self, address)


@pytest.fixture(autouse=True)
def no_real_remote(monkeypatch):
    """Fail any test that would fetch or push the real data branch, call GitHub, or open a network connection."""
    monkeypatch.setattr(subprocess, "run", _guarded_run)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
