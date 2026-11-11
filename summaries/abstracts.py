"""Abstracts of feed papers, kept in this machine's work folder and never published.

Publisher abstracts are often copyrighted and the data branch is public
(spec S1, Q3), so the feed's abstracts go to `<work dir>/abstracts.jsonl`,
one {"id", "abstract"} per line, and the summary step reads them from there.
A paper whose abstract is not here (another machine, a cleared cache) is
listed without a summary rather than left pending.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

FILE_NAME = "abstracts.jsonl"


def path(work_dir: str | Path) -> Path:
    return Path(work_dir) / FILE_NAME


def load(work_dir: str | Path) -> dict[str, str]:
    """{id: abstract}; a later line for the same id wins; unreadable lines are skipped."""
    found: dict[str, str] = {}
    file = path(work_dir)
    if not file.exists():
        return found
    for line in file.read_text(encoding="utf-8").splitlines():
        try:
            entry: Any = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        fields = cast("dict[str, object]", entry)
        paper_id, abstract = fields.get("id"), fields.get("abstract")
        if isinstance(paper_id, str) and isinstance(abstract, str):
            found[paper_id] = abstract
    return found


def save(work_dir: str | Path, abstracts: Mapping[str, str]) -> None:
    """Append {id: abstract} to the work folder's file."""
    if not abstracts:
        return
    file = path(work_dir)
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "a", encoding="utf-8") as fh:
        fh.writelines(json.dumps({"id": i, "abstract": a}, ensure_ascii=False) + "\n" for i, a in abstracts.items())
