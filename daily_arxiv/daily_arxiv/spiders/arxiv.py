import os
import re
from datetime import date, datetime, timedelta

import scrapy

ARXIV_ID = re.compile(r"^(\d{4})\.\d{4,5}$")
CATEGORY_CODE = re.compile(r"\(([a-z\-]+(?:\.[A-Za-z\-]+)?)\)")
# A code repository beats a project page when a paper links both.
CODE_REPO = re.compile(
    r"^https?://(?:(?:github\.com|gitlab\.com|codeberg\.org)/[\w.-]+/[\w.-]+"
    r"|anonymous\.4open\.science/r/[\w.-]+)"
)
PROJECT_PAGE = re.compile(r"^https?://[\w-]+\.git(?:hub|lab)\.io(?:/[\w.\-/]*)?")
# "Fri, 6 Nov 2026 (showing 11 of 11 entries )", or "(continued, showing ...)" on a later page.
DAY_HEADING = re.compile(r"^\s*\w{3}, (\d{1,2} \w{3} \d{4})")
TOTAL = re.compile(r"Total of (\d+) entries")
PAGE_SIZE = 2000


def _text(selector):
    """Whitespace-normalised text of a selector, without its 'Label:' descriptor."""
    if not selector:
        return ""
    text = " ".join(selector.xpath("string(.)").get().split())
    return re.sub(r"^(Title|Comments|Subjects):\s*", "", text)


class ArxivSpider(scrapy.Spider):
    """Read each category's /new listing, which carries every field we need.

    Keeps "New submissions" and "Cross-lists"; skips "Replacements" and
    late cross-lists of papers numbered before the month of the day's
    oldest new submission. Titles, authors and abstracts come from the
    listing itself, so no per-paper arXiv API call is needed.
    """

    name = "arxiv"
    allowed_domains = ["arxiv.org"]

    def __init__(self, categories=None, listing="new", *args, **kwargs):
        super().__init__(*args, **kwargs)
        raw = categories or os.environ.get("CATEGORIES", "cs.CV")
        self.target_categories = {c.strip() for c in raw.split(",") if c.strip()}
        self.listing = listing
        if listing == "recent":
            # The last five announcements, one <dl> per day, without abstracts.
            self.start_urls = [self._recent_url(cat, 0) for cat in self.target_categories]
        else:
            self.start_urls = [
                f"https://arxiv.org/list/{cat}/new?show=2000" for cat in self.target_categories
            ]

    @staticmethod
    def _recent_url(category, skip):
        return f"https://arxiv.org/list/{category}/recent?skip={skip}&show={PAGE_SIZE}"

    @staticmethod
    def cross_list_cutoff(new_papers, today=None):
        """YYMM before which a cross-list counts as late.

        The month of the oldest new submission on the page; for a listing
        without new submissions, the month of one week ago.
        """
        months = [m.group(1) for p in new_papers if (m := ARXIV_ID.match(p["id"]))]
        if months:
            return min(months)
        week_ago = (date.fromisoformat(today) if today else date.today()) - timedelta(days=7)
        return week_ago.strftime("%y%m")

    @staticmethod
    def is_late_cross_list(arxiv_id, oldest_new_month):
        match = ARXIV_ID.match(arxiv_id)
        return bool(match and oldest_new_month and match.group(1) < oldest_new_month)

    def _sections(self, response):
        """Item numbers where the cross-list and replacement sections start."""
        starts = {}
        for link in response.css("div[id=dlpage] ul li a"):
            label = (link.css("::text").get() or "").lower()
            match = re.search(r"#item(\d+)$", link.attrib.get("href") or "")
            if not match:
                continue
            number = int(match.group(1))
            if "cross" in label:
                starts["cross"] = number
            elif "replace" in label:
                starts["replace"] = number
        return starts.get("cross"), starts.get("replace")

    def _paper(self, dt, dd):
        arxiv_id = dt.css("a[title=Abstract]::attr(id)").get() or (
            dt.css("a[title=Abstract]::attr(href)").get() or ""
        ).split("/")[-1]
        primary = CATEGORY_CODE.findall(dd.css(".list-subjects .primary-subject::text").get() or "")
        listed = CATEGORY_CODE.findall(_text(dd.css(".list-subjects")))
        categories = list(dict.fromkeys(primary + listed))
        comment = _text(dd.css(".list-comments")) or None
        paper = {
            "id": arxiv_id.strip(),
            "categories": categories,
            "pdf": f"https://arxiv.org/pdf/{arxiv_id.strip()}",
            "abs": f"https://arxiv.org/abs/{arxiv_id.strip()}",
            "authors": [a.strip() for a in dd.css(".list-authors a::text").getall() if a.strip()],
            "title": _text(dd.css(".list-title")),
            "comment": comment,
            "summary": _text(dd.css("p.mathjax")),
        }
        code_url = self._code_url(dd)
        if code_url:
            paper["code_url"] = code_url
        return paper

    @staticmethod
    def _code_url(dd):
        links = dd.css("p.mathjax a::attr(href), .list-comments a::attr(href)").getall()
        for pattern in (CODE_REPO, PROJECT_PAGE):
            for link in links:
                match = pattern.match(link)
                if match:
                    return match.group(0).rstrip(".,)").removesuffix(".git")
        return None

    def parse(self, response):
        if self.listing == "recent":
            yield from self.parse_recent(response)
            return
        cross_start, replace_start = self._sections(response)
        new, cross = [], []
        for dt in response.css("div[id=dlpage] dl dt"):
            anchor = dt.css("a[name^='item']::attr(name)").get()
            dd = dt.xpath("following-sibling::dd[1]")
            if not anchor or not dd:
                continue
            number = int(anchor.split("item")[-1])
            if replace_start is not None and number >= replace_start:
                continue
            section = cross if cross_start is not None and number >= cross_start else new
            section.append(self._paper(dt, dd))

        oldest_new_month = self.cross_list_cutoff(new)
        for paper in new:
            yield paper
        for paper in cross:
            if self.is_late_cross_list(paper["id"], oldest_new_month):
                self.logger.info(f"Skipping late cross-list {paper['id']}")
                continue
            yield paper

    def parse_recent(self, response):
        """Papers of the recent listing, each tagged with the day it was announced ("announced").

        The listing does not separate cross-lists, so a paper whose primary
        category is another one counts as a late cross-list when it is numbered
        before the month of that day's oldest paper of this category.
        """
        category = re.search(r"/list/([^/]+)/recent", response.url).group(1)
        for block in response.css("div[id=dlpage] dl"):
            heading = DAY_HEADING.match(block.css("h3::text").get() or "")
            if not heading:
                continue
            day = datetime.strptime(heading.group(1), "%d %b %Y").date().isoformat()
            papers = [self._paper(dt, dt.xpath("following-sibling::dd[1]")) for dt in block.css("dt")]
            own = [p for p in papers if p["categories"][:1] == [category]]
            cutoff = self.cross_list_cutoff(own, today=day)
            for paper in papers:
                if paper["categories"][:1] != [category] and self.is_late_cross_list(paper["id"], cutoff):
                    self.logger.info(f"Skipping late cross-list {paper['id']}")
                    continue
                yield {**paper, "announced": day}
        total = TOTAL.search(response.text)
        skip = int(re.search(r"skip=(\d+)", response.url).group(1)) if "skip=" in response.url else 0
        if total and skip + PAGE_SIZE < int(total.group(1)):
            yield response.follow(self._recent_url(category, skip + PAGE_SIZE), callback=self.parse)
