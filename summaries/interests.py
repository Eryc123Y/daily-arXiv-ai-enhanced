"""Interest topics and keyword matching, the same as the reading page's.

Topics come from js/interest-presets.js, and a keyword matches as in
js/paper-data.js: a whole word or phrase, hyphens and spaces interchangeable,
with an optional plural "s"/"es", over the title, abstract and TL;DR. Case
does not matter, except for a name: a one-word keyword with a capital first
letter and a lowercase letter after it ("Lean", "BabyLM") matches only as
written, so "Lean" the proof assistant is not "lean" the adjective.
"""

import re
from functools import lru_cache
from pathlib import Path

PRESETS = Path(__file__).resolve().parent.parent / "js" / "interest-presets.js"
SEPARATOR = r"[\s\-‐-—_/]+"
TOPIC = re.compile(r"name:\s*'([^']+)',\s*keywords:\s*\[(.*?)\]", re.DOTALL)
QUOTED = re.compile(r"'([^']+)'")


def load_topics(path=PRESETS):
    """[{name, keywords}] in the page's order."""
    text = Path(path).read_text(encoding="utf-8")
    body = text.split("const TOPICS", 1)[1].split("];", 1)[0]
    return [{"name": name, "keywords": QUOTED.findall(words)} for name, words in TOPIC.findall(body)]


def _is_name(words):
    word = words[0] if len(words) == 1 else ""
    return bool(word) and word[0].isupper() and any(c.islower() for c in word[1:])


def _caseless(text):
    """`text` as a pattern that matches it in any case, one character class per cased letter."""
    def one(c):
        lower, upper = c.lower(), c.upper()
        return f"[{lower}{upper}]" if lower != upper and len(lower) == len(upper) == 1 else re.escape(c)

    return "".join(map(one, text))


def _term_pattern(term):
    words = [w for w in re.split(SEPARATOR, term.strip()) if w]
    if not words:
        return None
    if _is_name(words):
        return f"{re.escape(words[0])}(?:e?s)?"
    return f"{SEPARATOR.join(map(_caseless, words))}(?:[eE]?[sS])?"


@lru_cache(maxsize=256)
def _keyword_regex(terms):
    patterns = [p for p in map(_term_pattern, sorted(terms, key=len, reverse=True)) if p]
    if not patterns:
        return None
    return re.compile(rf"(^|[^A-Za-z0-9])({'|'.join(patterns)})(?![A-Za-z0-9])")


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
