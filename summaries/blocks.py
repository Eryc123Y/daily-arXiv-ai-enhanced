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
"""

import re

from summaries.records import AI_FIELDS, clean_ai

HEADER = re.compile(r"^===\s*(\S+)\s*$")
LABEL = re.compile(r"^[\s>*_`#-]*([A-Za-z]+)[*_`]*\s*[:：]\s*(.*)$")


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
        if key in AI_FIELDS:
            fields[key] = label.group(2).strip()
            last = key
        elif last is not None:
            fields[last] = f"{fields[last]} {line.strip()}".strip()
    return fields


def parse_blocks(text):
    """Return ({paper_id: ai_fields}, [problem descriptions])."""
    summaries = {}
    problems = []
    for paper_id, lines in _split_blocks(text):
        ai = clean_ai(_parse_fields(lines))
        if ai is None:
            problems.append(f"{paper_id}: incomplete block")
        elif paper_id in summaries:
            problems.append(f"{paper_id}: duplicate block ignored")
        else:
            summaries[paper_id] = ai
    return summaries, problems
