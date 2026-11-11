"""The GitHub CLI and the repository this checkout publishes to."""

import json
import os
import re
import subprocess
from pathlib import Path

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


SITES = Path(__file__).with_name("sites.json")


def site_url(slug, sites=SITES):
    """Address of the reading page for owner/name.

    An entry under "addresses" in summaries/sites.json (repository slugs compared
    without case) wins; otherwise GitHub Pages: https://<owner>.github.io/<name>/,
    or https://<owner>.github.io/ for a repository named <owner>.github.io. Forks
    that host on GitHub Pages need no entry.
    """
    try:
        addresses = json.loads(Path(sites).read_text(encoding="utf-8")).get("addresses", {})
    except FileNotFoundError:
        addresses = {}
    configured = {key.lower(): value for key, value in addresses.items()}.get(slug.lower())
    if configured:
        return configured.rstrip("/") + "/"
    owner, name = slug.split("/", 1)
    owner = owner.lower()
    return f"https://{owner}.github.io/" if name.lower() == f"{owner}.github.io" else f"https://{owner}.github.io/{name}/"


def gh(*args):
    """Run the GitHub CLI as the user it is logged in as."""
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True, timeout=GH_TIMEOUT).stdout
