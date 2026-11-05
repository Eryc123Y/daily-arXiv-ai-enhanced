"""The GitHub CLI and the repository this checkout publishes to."""

import os
import re
import subprocess

GITHUB_REMOTE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
GH_TIMEOUT = 120


def parse_repo_slug(url):
    match = GITHUB_REMOTE.search(url.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def repo_slug(repo_dir):
    """owner/name of the GitHub repository: DATA_REPO, GITHUB_REPOSITORY, else the origin remote."""
    for name in ("DATA_REPO", "GITHUB_REPOSITORY"):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    url = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=str(repo_dir), capture_output=True, text=True
    ).stdout
    slug = parse_repo_slug(url)
    if not slug:
        raise SystemExit("Cannot tell which GitHub repository this is; set DATA_REPO=owner/name.")
    return slug


def gh(*args):
    """Run the GitHub CLI as the user it is logged in as."""
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True, timeout=GH_TIMEOUT).stdout
