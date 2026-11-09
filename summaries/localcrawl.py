"""The arXiv crawl, run on this machine by `ensure-day`.

Today's papers come from each category's /new page, which lists only the
latest announcement with full abstracts. Days the machine missed come from
the /recent pages, which list the last five announcements by day but without
abstracts; those are then read from the arXiv API. Categories are the
CATEGORIES repository variable, as the old Actions crawl used.
"""

import os
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from summaries import github
from summaries.records import parse_jsonl

# Used when the CATEGORIES repository variable is unset.
DEFAULT_CATEGORIES = "cs.CV, cs.AI, cs.LG, cs.CL, stat.ML"
CRAWL_TIMEOUT = 30 * 60
API_URL = "https://export.arxiv.org/api/query"
API_BATCH = 100
API_PAUSE = 3  # seconds between API calls, as arXiv asks
API_TIMEOUT = 60
USER_AGENT = "daily-arxiv-ai-enhanced (local crawl)"
ATOM = "{http://www.w3.org/2005/Atom}"
VERSION = re.compile(r"v\d+$")


@dataclass(frozen=True)
class Listing:
    days: dict  # day -> papers with abstracts, for the days asked for
    covered: list  # every day the /recent listing showed, oldest first


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


def run_spider(repo_dir, slug, listing="new"):
    """Run the spider from `repo_dir` and return its rows; CrawlError if it finds none."""
    env = {**os.environ, "CATEGORIES": categories(slug)}
    cmd = ["uv", "run", "scrapy", "crawl", "arxiv", "-L", "INFO"]
    if listing != "new":
        cmd += ["-a", f"listing={listing}"]
    with tempfile.TemporaryDirectory(prefix="arxiv-crawl-") as tmp:
        out = Path(tmp) / "crawl.jsonl"
        try:
            subprocess.run(
                [*cmd, "-o", str(out)],
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


def crawl(repo_dir, slug):
    """Today's announcement from the /new pages."""
    return run_spider(repo_dir, slug)


def recent(repo_dir, slug, wanted):
    """The /recent listing: the `wanted` days' papers, with abstracts read from the arXiv API."""
    rows = run_spider(repo_dir, slug, listing="recent")
    covered = sorted({r["announced"] for r in rows if r.get("announced")})
    chosen = [r for r in rows if r.get("announced") in set(wanted)]
    abstracts = fetch_abstracts(list(dict.fromkeys(r["id"] for r in chosen))) if chosen else {}
    days = {}
    for row in chosen:
        if abstracts.get(row["id"]):
            paper = {k: v for k, v in row.items() if k != "announced"}
            days.setdefault(row["announced"], []).append({**paper, "summary": abstracts[row["id"]]})
    return Listing(days=days, covered=covered)


def fetch_abstracts(ids):
    """{arXiv id: abstract} from the arXiv API, API_BATCH ids per call."""
    found = {}
    for start in range(0, len(ids), API_BATCH):
        if start:
            time.sleep(API_PAUSE)
        batch = ids[start : start + API_BATCH]
        query = urlencode({"id_list": ",".join(batch), "max_results": len(batch)})
        try:
            with urlopen(Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT}), timeout=API_TIMEOUT) as response:
                feed = ET.fromstring(response.read())
        except (URLError, OSError, ET.ParseError) as error:
            raise CrawlError(f"the arXiv API did not answer: {error}") from error
        for entry in feed.iter(f"{ATOM}entry"):
            arxiv_id = VERSION.sub("", (entry.findtext(f"{ATOM}id") or "").rsplit("/abs/", 1)[-1])
            summary = " ".join((entry.findtext(f"{ATOM}summary") or "").split())
            if arxiv_id and summary:
                found[arxiv_id] = summary
    return found
