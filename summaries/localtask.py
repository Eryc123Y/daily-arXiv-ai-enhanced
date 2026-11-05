"""The local summary task's work folder: the run lock, chunk files for subagents, and merging their outputs."""

import os
import time
from datetime import datetime
from pathlib import Path

from summaries.blocks import format_chunk, parse_blocks
from summaries.datafiles import (
    ai_path,
    counts,
    make_branch,
    publish_summaries,
    raw_path,
    read_records,
)
from summaries.prompting import instructions
from summaries.records import AI_FIELDS, pending_papers

LOCK_TTL_SECONDS = 3 * 3600


def work_dir(args, day):
    return Path(args.work_dir) / day


def acquire_lock(root, force):
    """Create the run lock atomically; return the current holder if it is taken."""
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "LOCK"
    if lock.exists() and (force or time.time() - lock.stat().st_mtime >= LOCK_TTL_SECONDS):
        lock.unlink(missing_ok=True)
    try:
        with open(lock, "x", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n")
    except FileExistsError:
        return lock.read_text(encoding="utf-8").strip() or "unknown"
    return None


def release_lock(root):
    (root / "LOCK").unlink(missing_ok=True)


def collect_outputs(directory):
    summaries, problems = {}, []
    for out in sorted(directory.glob("*.out.txt")):
        found, issues = parse_blocks(out.read_text(encoding="utf-8"))
        problems += [f"{out.name}: {issue}" for issue in issues]
        for paper_id, ai in found.items():
            summaries.setdefault(paper_id, ai)
    return summaries, problems


def merge_outputs(args):
    directory = work_dir(args, args.date)
    outputs = sorted(directory.glob("*.out.txt")) if directory.exists() else []
    summaries, problems = collect_outputs(directory) if outputs else ({}, [])
    branch = make_branch(args)
    branch.fetch()
    known = {p["id"] for p in read_records(branch, raw_path(args.date))}
    unknown = sorted(set(summaries) - known)
    problems += [f"{paper_id}: not in the day's raw file" for paper_id in unknown]
    stats = publish_summaries(branch, args.date, args.language, summaries, "claude-code")
    archive = directory / "merged"
    for out in outputs:
        archive.mkdir(parents=True, exist_ok=True)
        out.rename(archive / f"{int(time.time())}-{out.name}")
    return {"date": args.date, "parsed": len(summaries), "problems": problems[:30], **stats}


def write_chunks(args):
    """Write INSTRUCTIONS.md and chunk inputs for the day's pending papers; return the plan."""
    directory = work_dir(args, args.date)
    leftovers = None
    if directory.exists() and any(directory.glob("*.out.txt")):
        leftovers = merge_outputs(args)
    for stale in directory.glob("*.in.txt") if directory.exists() else []:
        stale.unlink()
    directory.mkdir(parents=True, exist_ok=True)

    branch = make_branch(args)
    branch.fetch()
    raw = read_records(branch, raw_path(args.date))
    ai_records = read_records(branch, ai_path(args.date, args.language))
    todo = pending_papers(raw, ai_records)
    guide = directory / "INSTRUCTIONS.md"
    guide.write_text(subagent_instructions(args.language), encoding="utf-8")
    chunks = []
    for index in range(0, len(todo), args.chunk_size):
        part = todo[index : index + args.chunk_size]
        stem = directory / f"chunk-{index // args.chunk_size:03d}"
        Path(f"{stem}.in.txt").write_text(format_chunk(part), encoding="utf-8")
        chunks.append({"input": f"{stem}.in.txt", "output": f"{stem}.out.txt", "papers": len(part)})
    return {
        "date": args.date,
        **counts(raw, ai_records),
        "merged_leftovers": leftovers,
        "instructions": str(guide),
        "chunks": chunks,
    }


def subagent_instructions(language):
    fields = "\n".join(f"{name}: ..." for name in AI_FIELDS)
    return f"""# Summarise arXiv papers

{instructions(language)}

## Input
The input file holds one block per paper: a line `=== <arXiv id>`, then a `title:` line and an `abstract:` line.

## Output
Use the Write tool to write the output file with one block per input paper, in input order, exactly in this format:

=== <arXiv id>
{fields}

Rules:
- Every paper in the input gets a block. Copy each `=== <arXiv id>` line exactly.
- Field names stay in English as shown; field contents are in {language}.
- Each field is a single line. No Markdown, no blank fields, nothing else in the file.

When the file is written, reply with only: done <number of blocks written>
"""
