"""Plain-text block format exchanged with the summary subagents.

Subagents read papers and write summaries as labelled lines instead of JSON,
because abstracts are full of LaTeX backslashes and quotes that a model
escapes unreliably. One block per paper:

    === 2610.12345
    tldr: ...
    motivation: ...
    method: ...
    result: ...
    conclusion: ...

A block whose fields all sit on one line (`tldr: ... motivation: ... method: ...`)
is split on the field labels when the line-by-line reading leaves it incomplete.
"""

import re

from summaries.records import AI_FIELDS, clean_ai

HEADER = re.compile(r"^===\s*(\S+)\s*$")
LABEL = re.compile(r"^[\s>*_`#-]*([A-Za-z]+)[*_`]*\s*[:：]\s*(.*)$")
INLINE_LABEL = re.compile(r"(?<![A-Za-z])[*_`]*(" + "|".join(AI_FIELDS) + r")[*_`]*\s*[:：]", re.IGNORECASE)


def _one_line(text):
    return " ".join((text or "").split())


def format_chunk(papers):
    """Render papers as the subagent's input file."""
    blocks = [
        f"=== {p['id']}\ntitle: {_one_line(p.get('title'))}\nabstract: {_one_line(p.get('summary'))}\n"
        for p in papers
    ]
    return "\n".join(blocks)


def _split_blocks(text):
    blocks = []
    current = None
    for line in text.splitlines():
        header = HEADER.match(line.strip())
        if header:
            current = (header.group(1), [])
            blocks.append(current)
        elif current is not None:
            current[1].append(line)
    return blocks


def _parse_fields(lines):
    fields = {}
    last = None
    for line in lines:
        if not line.strip():
            continue
        label = LABEL.match(line)
        key = label.group(1).lower() if label else None
        if label and key in AI_FIELDS:
            fields[key] = label.group(2).strip()
            last = key
        elif last is not None:
            fields[last] = f"{fields[last]} {line.strip()}".strip()
    return fields


def _parse_inline(lines):
    """Fields from the block's text split on the field labels wherever they stand.

    The first label of each field starts it; a later repeat of a label it already has is kept as text.
    """
    text = " ".join(line.strip() for line in lines if line.strip())
    starts, seen = [], set()
    for match in INLINE_LABEL.finditer(text):
        key = match.group(1).lower()
        if key not in seen:
            seen.add(key)
            starts.append((key, match))
    ends = [match.start() for _, match in starts[1:]] + [len(text)]
    return {key: text[match.end() : end].strip() for (key, match), end in zip(starts, ends, strict=True)}


def block_ids(text):
    """The paper ids of the `=== <id>` headers in `text`, in order."""
    return [paper_id for paper_id, _ in _split_blocks(text)]


def parse_blocks(text):
    """Return ({paper_id: ai_fields}, [problem descriptions])."""
    summaries = {}
    problems = []
    for paper_id, lines in _split_blocks(text):
        ai = clean_ai(_parse_fields(lines)) or clean_ai(_parse_inline(lines))
        if ai is None:
            problems.append(f"{paper_id}: incomplete block")
        elif paper_id in summaries:
            problems.append(f"{paper_id}: duplicate block ignored")
        else:
            summaries[paper_id] = ai
    return summaries, problems
