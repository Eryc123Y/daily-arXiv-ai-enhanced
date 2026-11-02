"""Interest topics and keyword matching, the same as the reading page's.

Topics come from js/interest-presets.js, and a keyword matches as in
js/paper-data.js: a whole word or phrase, case-insensitive, hyphens and spaces
interchangeable, with an optional plural "s"/"es", over the title, abstract
and TL;DR.
"""

import re
from functools import lru_cache
from pathlib import Path

PRESETS = Path(__file__).resolve().parent.parent / "js" / "interest-presets.js"
SEPARATOR = r"[\s\-‐-—_/]+"
TOPIC = re.compile(r"name:\s*'([^']+)',\s*keywords:\s*\[(.*?)\]", re.S)
QUOTED = re.compile(r"'([^']+)'")


def load_topics(path=PRESETS):
    """[{name, keywords}] in the page's order."""
    text = Path(path).read_text(encoding="utf-8")
    body = text.split("const TOPICS", 1)[1].split("];", 1)[0]
    return [{"name": name, "keywords": QUOTED.findall(words)} for name, words in TOPIC.findall(body)]


def _term_pattern(term):
    words = [re.escape(w) for w in re.split(SEPARATOR, term.strip()) if w]
    return f"{SEPARATOR.join(words)}(?:e?s)?" if words else None


@lru_cache(maxsize=256)
def _keyword_regex(terms):
    patterns = [p for p in map(_term_pattern, sorted(terms, key=len, reverse=True)) if p]
    if not patterns:
        return None
    return re.compile(rf"(^|[^A-Za-z0-9])({'|'.join(patterns)})(?![A-Za-z0-9])", re.I)


def keyword_matches(text, keyword):
    regex = _keyword_regex((keyword,))
    return bool(text and regex and regex.search(text))


def paper_text(record):
    ai = record.get("AI") or {}
    return " ".join(filter(None, [record.get("title"), record.get("summary"), ai.get("tldr")]))


def topics_for(record, topics):
    """Names of the topics whose keywords appear in the paper."""
    text = paper_text(record)
    found = []
    for topic in topics:
        regex = _keyword_regex(tuple(topic["keywords"]))
        if text and regex and regex.search(text):
            found.append(topic["name"])
    return found
