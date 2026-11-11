"""Record shapes, named once (types only; nothing here runs).

A day's raw file `data/<date>.jsonl` holds arXiv records and, since the
sources spec (docs/specs/s1-sources-beyond-arxiv.md), feed records. A record
without `source` is an arXiv record: old days and forks keep working. The
summary file holds the same records with an `AI` object added.
"""

from typing import Literal, NotRequired, TypedDict

FeedSource = Literal["openalex", "crossref", "openreview", "acl-anthology", "pmlr", "datacite", "jmlr"]


class AISummary(TypedDict):
    tldr: str
    motivation: str
    method: str
    result: str
    conclusion: str


class ArxivRecord(TypedDict):
    """One paper from arXiv's listings, as the spider writes it."""

    id: str  # arXiv ID without version, e.g. "2611.01234"
    categories: list[str]
    title: str
    authors: list[str]
    summary: str  # the abstract
    abs: str
    pdf: str
    comment: NotRequired[str | None]
    code_url: NotRequired[str | None]
    source: NotRequired[Literal["arxiv"]]  # absent on every record written so far
    # Set once the paper is published ("published in IEEE TCSVT"); the page shows them.
    # Nothing writes them yet (S1 spec, "Should have").
    venue: NotRequired[str]
    doi: NotRequired[str]
    AI: NotRequired[AISummary]


class FeedRecord(TypedDict):
    """One paper from the feed, as published. Its abstract is never published (the data branch is public);
    it stays in the local work folder for the summary step, keyed by `id`."""

    id: str  # the arXiv ID if the paper has one, else "doi:<doi>", else "openreview:<forum id>", else "url:<url>"
    source: FeedSource
    title: str
    authors: list[str]
    venue: str
    published: str  # YYYY-MM-DD, the source's publication date
    doi: str | None  # lower case, without the https://doi.org/ prefix
    oa_url: str | None  # a lawful open-access copy, when the source knows one
    url: str  # the publisher's or OpenReview's page
    categories: list[str]  # always empty; kept so readers that expect it need no special case
    has_abstract: bool  # an abstract was received (it stays local): a summary can be written for this paper
    code_url: NotRequired[str | None]  # the page shows it when present; the feed does not set it yet


class FeedLine(TypedDict):
    """One line of the feed command's output (the contract with LitScout's `watch`)."""

    source: FeedSource
    title: str
    authors: list[str]
    venue: str
    published: str
    doi: str | None
    arxiv_id: str | None
    openreview_id: str | None
    abstract: str | None
    oa_url: str | None
    url: str


class FeedCursor(TypedDict):
    """`assets/feed-cursor.json`: the next run asks the feed for papers since this day."""

    since: str
    at: str


class Venue(TypedDict):
    """One entry of `summaries/watchlist.json`."""

    name: str
    kind: Literal["conference", "journal"]
    group: str
    area: NotRequired[str]  # the page's Area selector, e.g. "Graphics and VR"
    match: NotRequired[Literal["all", "topics"]]  # "topics": only papers matching an interest keyword (default "all")
    top: NotRequired[bool]  # a flagship venue: "Top conferences" or "Top journals" on the page (default false)
    issn: NotRequired[list[str]]
    openalex_source: NotRequired[str]  # e.g. "S4210173141"
    openreview_venues: NotRequired[list[str]]  # e.g. ["ICLR.cc/2026/Conference"]
    # Read by LitScout's watch command (contract of 2026-11-12); other fields LitScout adds pass through.
    jmlr: NotRequired[bool]  # true: jmlr.org's own feed
    acl_anthology: NotRequired[str]  # ACL Anthology venue id, e.g. "acl", "tacl"
    pmlr: NotRequired[str]  # PMLR series as in "Proceedings of COLT 2026", e.g. "COLT"
    doi_prefix: NotRequired[str]  # e.g. "10.4230/LIPIcs.ITP"
    openreview: NotRequired[str | list[str]]  # OpenReview venue id(s); "{year}" is expanded, e.g. "colmweb.org/COLM/{year}/Conference"
    sources: NotRequired[list[FeedSource]]


class VenueSummary(TypedDict):
    """One entry of `assets/venues.json`, the public part of the watch list the page groups venues by."""

    name: str
    kind: Literal["conference", "journal"]
    area: str | None
    top: bool  # a flagship venue; the page lists the others under "Other venues"
