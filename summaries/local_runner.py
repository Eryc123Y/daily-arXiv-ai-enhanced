"""Run the local summary job through any coding-agent CLI.

`uv run python -m summaries run-local --client codex` does what the Claude
Code scheduled task does, without Claude-specific tools: for each recent
day with pending papers it writes the chunk files, gives each chunk to the
client's headless command (a few at a time), merges and pushes the results,
logs the day's path as `local-<client>` and releases the lock. The prompt
goes to the client as one argument, never through a shell. Only Claude
exposes plan usage, so other clients get a per-run budget (--max-chunks).
"""

import json
import subprocess
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from summaries import cli

CHUNK_TIMEOUT = 900
run_command = subprocess.run


def chunk_prompt(instructions, input_path, output_path):
    return (
        f"Read {instructions} and follow it exactly. Input file: {input_path}. Output file: {output_path}. "
        "Only read those two files and write the output file; do not run shell commands or edit anything else."
    )


def client_argv(client, prompt, model=None, command=None):
    """The headless command line for one chunk."""
    if client == "claude":
        return ["claude", "-p", prompt, "--model", model or "haiku", "--allowedTools", "Read,Write"]
    if client == "codex":
        return ["codex", "exec", "--sandbox", "workspace-write", *(["-m", model] if model else []), prompt]
    if client == "antigravity":
        return ["agy", "-p", prompt, *(["--model", model] if model else [])]
    if client == "custom":
        if not command:
            raise ValueError("--client custom needs --command, a JSON list with {prompt} (and optionally {model})")
        template = json.loads(command)
        return [part.replace("{prompt}", prompt).replace("{model}", model or "") for part in template]
    raise ValueError(f"unknown client '{client}' (use claude, codex, antigravity or custom)")


def run_chunk(chunk, plan, args):
    """Run one chunk; return a problem description, or None when the output file was written."""
    name = Path(chunk["input"]).name
    argv = client_argv(args.client, chunk_prompt(plan["instructions"], chunk["input"], chunk["output"]), args.model, args.command)
    try:
        result = run_command(argv, cwd=args.repo, capture_output=True, text=True, timeout=CHUNK_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"{name}: no answer within {CHUNK_TIMEOUT // 60} minutes"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-1:] or [""]
        return f"{name}: {argv[0]} exited with {result.returncode}: {detail[0][:200]}"
    if not Path(chunk["output"]).exists():
        return f"{name}: {argv[0]} finished without writing the output file"
    return None


def summarise_day(day_args, args, budget):
    """Prepare, run and merge one day; return (chunks run, failures)."""
    plan = cli.write_chunks(day_args)
    chunks = plan["chunks"] if budget is None else plan["chunks"][:budget]
    failures = []
    for start in range(0, len(chunks), args.merge_every):
        batch = chunks[start : start + args.merge_every]
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            failures += [f for f in pool.map(lambda c: run_chunk(c, plan, args), batch) if f]
        cli.merge_outputs(day_args)
    return len(chunks), failures


def cmd_run_local(args):
    client_argv(args.client, "probe", args.model, args.command)  # fail fast on a bad client setting
    root = Path(args.work_dir)
    holder = cli.acquire_lock(root, False)
    if holder:
        cli.emit(locked=True, holder=holder)
        return 3
    report = {"client": args.client, "dates": [], "failures": [], "stopped": None}
    budget = args.max_chunks
    try:
        branch = cli.make_branch(args)
        branch.fetch()
        for day in cli.recent_days(branch, args.days):
            stats = cli.counts(cli.read_records(branch, cli.raw_path(day)), cli.read_records(branch, cli.ai_path(day, args.language)))
            if stats["pending"] == 0:
                continue
            if budget is not None and budget <= 0:
                report["stopped"] = "chunk budget reached"
                break
            day_args = Namespace(**{**vars(args), "date": day})
            ran, failures = summarise_day(day_args, args, budget)
            report["failures"] += failures
            if budget is not None:
                budget -= ran
            reason = f"{ran} chunks, {len(failures)} failed"
            entry = cli.record_run(branch, day, args.language, f"local-{args.client}", reason)
            report["dates"].append({k: entry[k] for k in ("date", "total", "done", "pending")})
            if budget is not None and budget <= 0 and entry["pending"] > 0:
                report["stopped"] = "chunk budget reached"
                break
    finally:
        cli.release_lock(root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def add_parser(sub):
    run = sub.add_parser("run-local", help="summarise pending papers with a local coding-agent CLI")
    run.add_argument("--client", required=True, choices=["claude", "codex", "antigravity", "custom"])
    run.add_argument("--model", help="model for the client (claude defaults to haiku)")
    run.add_argument("--command", help='custom client: JSON list, e.g. ["mycli","-p","{prompt}"]')
    run.add_argument("--parallel", type=int, default=2, help="chunks run at the same time")
    run.add_argument("--max-chunks", type=int, help="stop after this many chunks (usage budget)")
    run.add_argument("--merge-every", type=int, default=3, help="merge and push after this many chunks")
    run.add_argument("--chunk-size", type=int, default=20)
    run.add_argument("--days", type=int, default=4)
    run.set_defaults(func=cmd_run_local)
