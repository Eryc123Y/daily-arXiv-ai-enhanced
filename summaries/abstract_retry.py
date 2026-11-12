"""Fill missing feed abstracts by DOI or arXiv ID, whenever the paper was first listed.

The feed's re-request window (feed.RECHECK_DAYS) is keyed on the day a source
registered a paper, so a paper whose abstract reaches OpenAlex or a publisher
API later than that never gains one through the feed. ensure-day therefore
asks ABSTRACTS_COMMAND, a JSON argv list like FEED_COMMAND (LitScout's
`abstracts`), for the feed records of the last WINDOW_DAYS days that were
published with `has_abstract: false` and have no abstract in the work folder,
newest day first, at most MAX_ASKED.

The contract: stdin is JSON Lines, one {"id", "doi"?, "arxiv"?, "title"?} per
paper; stdout is one {"id", "abstract": string|null, "source": string|null}
per input line, in order; exit code 0 on a completed run. Any other answer
(a non-zero exit, a line that is not that object, ids out of order, too few
or too many lines) saves nothing. A push of the flags that fails is reported as
an error too, with the abstracts already saved.

Abstracts found go to the local file (abstracts.save) and their records get
`has_abstract: true` on the day they were first published, as the feed does
for its own re-requests; the text never reaches the public branch. Such a
paper is then pending for run-local like any other feed paper with a local
abstract.
"""

import json
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict, cast

from summaries import abstracts
from summaries.databranch import PublishError
from summaries.datafiles import raw_path
from summaries.feed import raw_days, with_abstracts_flagged
from summaries.records import dump_jsonl, is_arxiv

WINDOW_DAYS = 60
MAX_ASKED = 200
TIMEOUT = 20 * 60
ID_PREFIXES = ("doi:", "openreview:", "url:")

Record = dict[str, Any]


class Request(TypedDict, total=False):
    """One stdin line; `id` is always there, the rest when the record has them."""

    id: str
    doi: str
    arxiv: str
    title: str


class AbstractsError(RuntimeError):
    pass


def abstracts_command(env: Mapping[str, str]) -> list[str] | None:
    """ABSTRACTS_COMMAND as an argv list, or None when unset; AbstractsError when it is not a JSON list of strings."""
    raw = (env.get("ABSTRACTS_COMMAND") or "").strip()
    if not raw:
        return None
    try:
        argv: Any = json.loads(raw)
    except ValueError as error:
        raise AbstractsError('ABSTRACTS_COMMAND must be a JSON list, e.g. ["litscout", "abstracts"]') from error
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in cast("list[Any]", argv)):
        raise AbstractsError("ABSTRACTS_COMMAND must be a non-empty JSON list of strings")
    return cast("list[str]", argv)


def lacking(by_day: Mapping[str, Sequence[Any]], local: Mapping[str, str]) -> list[Record]:
    """Feed records published without an abstract and with none in the work folder, newest day first, each id once."""
    found: list[Record] = []
    seen: set[str] = set()
    for day in sorted(by_day, reverse=True):
        for item in by_day[day]:
            if not isinstance(item, dict):
                continue
            record = cast("Record", item)
            paper_id = record.get("id")
            if not isinstance(paper_id, str) or not paper_id or paper_id in seen or paper_id in local:
                continue
            if not is_arxiv(record) and record.get("has_abstract") is False:
                seen.add(paper_id)
                found.append(record)
    return found


def request(record: Record) -> Request:
    """The stdin line for one record: its DOI, its arXiv ID (an id without a prefix) and its title, when known."""
    paper_id = str(record["id"])
    line: Request = {"id": paper_id}
    doi, title = record.get("doi"), record.get("title")
    if isinstance(doi, str) and doi:
        line["doi"] = doi
    if not paper_id.startswith(ID_PREFIXES):
        line["arxiv"] = paper_id
    if isinstance(title, str) and title:
        line["title"] = title
    return line


def parse_reply(text: str, ids: Sequence[str]) -> dict[str, tuple[str | None, str | None]]:
    """{id: (abstract, source)} from the command's stdout; AbstractsError when it breaks the contract."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != len(ids):
        raise AbstractsError(f"the abstracts command answered {len(lines)} lines for {len(ids)} papers")
    found: dict[str, tuple[str | None, str | None]] = {}
    for number, (line, paper_id) in enumerate(zip(lines, ids, strict=True), start=1):
        found[paper_id] = _answer(line, paper_id, number)
    return found


def _answer(line: str, paper_id: str, number: int) -> tuple[str | None, str | None]:
    try:
        value: Any = json.loads(line)
    except ValueError as error:
        raise AbstractsError(f"line {number} of the abstracts command is not JSON") from error
    if not isinstance(value, dict):
        raise AbstractsError(f"line {number} of the abstracts command is not an object")
    entry = cast("dict[str, Any]", value)
    abstract, source = entry.get("abstract"), entry.get("source")
    if entry.get("id") != paper_id:
        raise AbstractsError(f"line {number} of the abstracts command is for {entry.get('id')!r}, not {paper_id!r}")
    if not (abstract is None or isinstance(abstract, str)) or not (source is None or isinstance(source, str)):
        raise AbstractsError(f"line {number} of the abstracts command has an abstract or source that is not a string or null")
    text = abstract.strip() if isinstance(abstract, str) else ""
    return (text or None), source


def run_command(argv: Sequence[str], stdin: str, cwd: str | Path) -> str:
    """The command's stdout; AbstractsError with its one-line reason when it fails."""
    try:
        result = subprocess.run(list(argv), cwd=str(cwd), input=stdin, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except (subprocess.TimeoutExpired, OSError) as error:
        raise AbstractsError(f"the abstracts command did not finish: {error}") from error
    if result.returncode != 0:
        reason = (result.stderr or "").strip().splitlines()[-1:] or [f"exit code {result.returncode}"]
        raise AbstractsError(f"the abstracts command failed: {reason[0][:200]}")
    return result.stdout


def flag_filled(branch: Any, day: str, filled: Mapping[str, str]) -> str:
    """Set `has_abstract: true` on the filled records' own days in one commit; the commit, or "" when none was needed."""

    def build(current: Any) -> dict[str, str]:
        by_day: dict[str, list[Any]] = raw_days(current, day, WINDOW_DAYS)
        return {
            raw_path(d): dump_jsonl(with_abstracts_flagged(records, filled))
            for d, records in by_day.items()
            if any(isinstance(r, dict) and cast("Record", r).get("id") in filled for r in records)
        }

    commit: str | None = branch.publish(build, f"update: abstracts found for {len(filled)} feed papers")
    return commit or ""


def run(branch: Any, day: str, repo_dir: str | Path, work_dir: str | Path, env: Mapping[str, str]) -> dict[str, Any]:
    """The `abstracts` part of ensure-day's report: {"status": "off"} without ABSTRACTS_COMMAND, else what was filled."""
    try:
        argv = abstracts_command(env)
    except AbstractsError as error:
        return {"status": "error", "reason": str(error)}
    if argv is None:
        return {"status": "off"}
    branch.fetch()
    wanted = lacking(raw_days(branch, day, WINDOW_DAYS), abstracts.load(work_dir))
    asked = wanted[:MAX_ASKED]
    report: dict[str, Any] = {"status": "ok", "asked": len(asked), "filled": 0, "by_source": {}, "still_lacking": len(wanted), "commit": ""}
    if not asked:
        return report
    stdin = "".join(json.dumps(request(r), ensure_ascii=False) + "\n" for r in asked)
    try:
        answers = parse_reply(run_command(argv, stdin, repo_dir), [str(r["id"]) for r in asked])
    except AbstractsError as error:
        return {**report, "status": "error", "reason": str(error)}
    filled = {paper_id: abstract for paper_id, (abstract, _) in answers.items() if abstract}
    sources = Counter(answers[paper_id][1] or "unknown" for paper_id in filled)
    # Saved before the push, as the feed does: a saved abstract without its flag is harmless, the reverse is not.
    abstracts.save(work_dir, filled)
    report = {**report, "filled": len(filled), "by_source": dict(sorted(sources.items())), "still_lacking": len(wanted) - len(filled)}
    try:
        commit = flag_filled(branch, day, filled) if filled else ""
    except PublishError as error:
        # The abstracts are saved, so the papers are pending all the same; only the public flag waits.
        return {**report, "status": "error", "reason": str(error)}
    return {**report, "commit": commit}
