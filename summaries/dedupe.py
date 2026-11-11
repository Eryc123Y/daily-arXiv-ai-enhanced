"""R2: a feed paper already on the data branch, or twice in one batch, is published once.

Matched by id (an arXiv ID, or a feed paper's openreview: or url: id), then
DOI, then normalised title plus the first author's family name. Titles by the same first author that are more than 90% alike
also match, so a journal version whose title gained a colon or lost a hyphen
is not published again.
"""

import re
import unicodedata
from dataclasses import replace
from difflib import SequenceMatcher

TITLE_SIMILARITY = 0.9
DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
ARXIV_PREFIX = re.compile(r"^arxiv:", re.IGNORECASE)
ARXIV_VERSION = re.compile(r"v\d+$")


def _ascii_words(text):
    folded = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in folded if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).split()


def normalise_title(title):
    return " ".join(_ascii_words(title))


def family_name(author):
    """The family name, lower case ASCII: "Lovelace, Ada" and "Ada Lovelace" both give "lovelace"."""
    name = (author or "").split(",")[0] if "," in (author or "") else (author or "")
    words = _ascii_words(name)
    return words[-1] if words else ""


def normalise_doi(doi):
    return DOI_PREFIX.sub("", (doi or "").strip()).lower() or None


def normalise_arxiv_id(arxiv_id):
    return ARXIV_VERSION.sub("", ARXIV_PREFIX.sub("", (arxiv_id or "").strip())) or None


def _keys(record):
    paper_id = record.get("id") or ""
    # The id names the paper, except a doi: id, which is matched by its DOI (any case, any prefix).
    same_id = paper_id if paper_id and not paper_id.startswith("doi:") else None
    doi = normalise_doi(record.get("doi")) or (paper_id[4:] if paper_id.startswith("doi:") else None)
    authors = record.get("authors") or [""]
    return same_id, doi, normalise_title(record.get("title")), family_name(authors[0])


class Index:
    """What is already published (owner None) or kept from this batch (owner the kept paper's position)."""

    def __init__(self):
        self.ids, self.dois, self.titles = {}, {}, {}

    def add(self, record, owner=None):
        same_id, doi, title, family = _keys(record)
        if same_id:
            self.ids.setdefault(same_id, owner)
        if doi:
            self.dois.setdefault(doi, owner)
        if title:
            self.titles.setdefault(family, {}).setdefault(title, owner)

    def find(self, record):
        """(matched, owner) for `record`."""
        same_id, doi, title, family = _keys(record)
        if same_id and same_id in self.ids:
            return True, self.ids[same_id]
        if doi and doi in self.dois:
            return True, self.dois[doi]
        same_author = self.titles.get(family, {})
        if title in same_author:
            return True, same_author[title]
        for known, owner in same_author.items():
            if SequenceMatcher(None, title, known).ratio() > TITLE_SIMILARITY:
                return True, owner
        return False, None


def _fill(kept, other):
    """`kept` with the fields it lacks taken from `other`, a copy of the same paper from another source."""
    record = {**kept.record, **{k: other.record[k] for k in ("doi", "oa_url") if not kept.record.get(k) and other.record.get(k)}}
    abstract = kept.abstract or other.abstract
    return replace(kept, record={**record, "has_abstract": bool(abstract)}, abstract=abstract)


def fresh(existing, batch):
    """(papers of `batch` to publish, number dropped as duplicates); copies within the batch are merged."""
    index = Index()
    for record in existing:
        index.add(record)
    kept = []
    for paper in batch:
        matched, owner = index.find(paper.record)
        if not matched:
            index.add(paper.record, owner=len(kept))
            kept.append(paper)
        elif owner is not None:
            kept[owner] = _fill(kept[owner], paper)
    return kept, len(batch) - len(kept)
