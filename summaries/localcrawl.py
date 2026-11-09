"""The arXiv crawl run on this machine, for days GitHub Actions cannot run it.

It does what the workflow's "Crawl arXiv listings" step does: the Scrapy
spider over the same categories (the CATEGORIES repository variable), whose
rows `ingest` then publishes. arXiv's /new pages only list the latest
announcement, so a local crawl can only stand in for today's run.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from summaries import github
from summaries.records import parse_jsonl

# The workflow's default when the CATEGORIES repository variable is unset.
DEFAULT_CATEGORIES = "cs.CV, cs.AI, cs.LG, cs.CL, stat.ML"
CRAWL_TIMEOUT = 30 * 60


class CrawlError(RuntimeError):
    pass


def categories(slug):
    """CATEGORIES from the environment, else the repository variable, else the workflow default."""
    if os.environ.get("CATEGORIES", "").strip():
        return os.environ["CATEGORIES"].strip()
    try:
        value = github.gh("variable", "get", "CATEGORIES", "-R", slug).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        value = ""
    return value or DEFAULT_CATEGORIES


def _last_line(error):
    text = (getattr(error, "stderr", None) or "").strip()
    return text.splitlines()[-1][:200] if text else str(error)


def crawl(repo_dir, slug):
    """Run the spider from `repo_dir` and return the listing rows; CrawlError if it finds none."""
    env = {**os.environ, "CATEGORIES": categories(slug)}
    with tempfile.TemporaryDirectory(prefix="arxiv-crawl-") as tmp:
        out = Path(tmp) / "crawl.jsonl"
        try:
            subprocess.run(
                ["uv", "run", "scrapy", "crawl", "arxiv", "-o", str(out), "-L", "INFO"],
                cwd=str(Path(repo_dir) / "daily_arxiv"),
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=CRAWL_TIMEOUT,
            )
        except subprocess.CalledProcessError as error:
            raise CrawlError(f"scrapy failed: {_last_line(error)}") from error
        except (subprocess.TimeoutExpired, OSError) as error:
            raise CrawlError(f"scrapy did not finish: {error}") from error
        rows = parse_jsonl(out.read_text(encoding="utf-8")) if out.exists() else []
    if not rows:
        raise CrawlError("the crawl returned no papers; arXiv may be unreachable")
    return rows
