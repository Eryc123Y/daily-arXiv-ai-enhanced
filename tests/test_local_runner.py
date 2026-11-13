import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import git, seed_data_branch
from summaries.cli import main
from summaries.local_runner import CHUNK_TIMEOUT, chunk_prompt, client_argv
from summaries.records import dump_jsonl, parse_jsonl

DAY = "2026-10-30"
AI_FILE = f"data/{DAY}_AI_enhanced_English.jsonl"
PROMPT = "Read /r/INSTRUCTIONS.md and follow it exactly."


def paper(paper_id):
    return {"id": paper_id, "categories": ["cs.CV"], "title": f"T{paper_id}", "authors": ["A"], "summary": f"S{paper_id}"}


def test_claude_runs_headless_with_haiku_and_only_file_tools():
    """Only Read and Write are loaded, and no MCP servers: their definitions would cost ~60k tokens per call."""
    assert client_argv("claude", PROMPT) == [
        "claude", "-p", PROMPT, "--model", "haiku", "--tools", "Read,Write", "--allowedTools", "Read,Write", "--strict-mcp-config",
    ]
    assert client_argv("claude", PROMPT, model="sonnet")[4] == "sonnet"


def test_codex_runs_exec_in_a_workspace_write_sandbox():
    assert client_argv("codex", PROMPT) == ["codex", "exec", "--sandbox", "workspace-write", PROMPT]
    assert client_argv("codex", PROMPT, model="m") == ["codex", "exec", "--sandbox", "workspace-write", "-m", "m", PROMPT]


def test_antigravity_runs_its_cli_headless_with_file_edits_only():
    """accept-edits approves the output file; commands are not approved, so headless agy refuses them instead of waiting.

    The prompt is the value of -p (agy reads no plain-text prompt from stdin), and agy stops itself before the
    runner's own timeout would kill it.
    """
    argv = client_argv("antigravity", PROMPT)
    assert argv[:3] == ["agy", "-p", PROMPT]
    assert argv[argv.index("--mode") + 1] == "accept-edits"
    assert {"--sandbox", "--disable-slash-commands"} <= set(argv)
    assert "--dangerously-skip-permissions" not in argv  # the chunks hold untrusted abstracts
    timeout = argv[argv.index("--print-timeout") + 1]
    assert timeout.endswith("s") and int(timeout[:-1]) < CHUNK_TIMEOUT
    assert "--model" not in argv
    assert client_argv("antigravity", PROMPT, model="m")[-2:] == ["--model", "m"]


def test_custom_commands_fill_the_prompt_and_model_placeholders():
    template = json.dumps(["mycli", "run", "--model", "{model}", "{prompt}"])
    assert client_argv("custom", PROMPT, model="x", command=template) == ["mycli", "run", "--model", "x", PROMPT]
    with pytest.raises(ValueError):
        client_argv("custom", PROMPT)
    with pytest.raises(ValueError):
        client_argv("cursor", PROMPT)


def test_chunk_prompt_names_the_instruction_input_and_output_files():
    prompt = chunk_prompt("/r/INSTRUCTIONS.md", "/r/chunk-000.in.txt", "/r/chunk-000.out.txt")
    for path in ("/r/INSTRUCTIONS.md", "/r/chunk-000.in.txt", "/r/chunk-000.out.txt"):
        assert path in prompt


FIELDS = "tldr: t\nmotivation: m\nmethod: x\nresult: r\nconclusion: c\n"


def fake_client(calls, fail=(), cwds=None):
    """Acts like a coding agent: reads the chunk named in the prompt and writes blocks."""

    def run(argv, cwd, capture_output, text, timeout, stdin):
        assert stdin is subprocess.DEVNULL
        calls.append(argv)
        if cwds is not None:
            cwds.append(cwd)
        prompt = next(a for a in argv if "Input file:" in a)
        source = re.search(r"Input file: (\S+?)\.(?:\s|$)", prompt).group(1)
        target = re.search(r"Output file: (\S+?)\.(?:\s|$)", prompt).group(1)
        ids = re.findall(r"^=== (\S+)$", Path(source).read_text(), flags=re.MULTILINE)
        if any(i in fail for i in ids):
            return SimpleNamespace(returncode=1, stdout="", stderr="model overloaded")
        Path(target).write_text("".join(f"=== {i}\n{FIELDS}\n" for i in ids))
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    return run


def run_local(clone, monkeypatch, capsys, runner, *extra):
    from summaries import local_runner

    monkeypatch.setattr(local_runner, "run_command", runner)
    code = main(["--repo", str(clone), "--work-dir", str(clone / ".cache" / "summaries"), "run-local", "--days", "36500", *extra])
    return code, json.loads(capsys.readouterr().out)


def test_run_local_summarises_every_pending_paper_and_logs_the_client(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper(str(i)) for i in range(5)])})
    calls = []

    code, report = run_local(clone, monkeypatch, capsys, fake_client(calls), "--client", "codex", "--chunk-size", "2")

    assert code == 0
    assert len(calls) == 3 and calls[0][:2] == ["codex", "exec"]
    assert [r["id"] for r in parse_jsonl(git(remote, "show", f"data:{AI_FILE}"))] == ["0", "1", "2", "3", "4"]
    assert report["dates"][0]["pending"] == 0
    log = parse_jsonl(git(remote, "show", "data:logs/summary-runs.jsonl"))[-1]
    assert (log["path"], log["done"]) == ("local-codex", 5)
    assert not (clone / ".cache" / "summaries" / "LOCK").exists()


def test_run_local_stops_at_the_chunk_budget_and_resumes_next_time(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper(str(i)) for i in range(4)])})

    _, report = run_local(clone, monkeypatch, capsys, fake_client([]), "--client", "antigravity", "--chunk-size", "1", "--max-chunks", "2")
    assert (report["dates"][0]["done"], report["dates"][0]["pending"]) == (2, 2)
    assert report["stopped"] == "chunk budget reached"

    _, report = run_local(clone, monkeypatch, capsys, fake_client([]), "--client", "antigravity", "--chunk-size", "1")
    assert report["dates"][0]["pending"] == 0


def test_a_failing_client_call_leaves_its_papers_pending(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})

    code, report = run_local(clone, monkeypatch, capsys, fake_client([], fail={"2"}), "--client", "claude", "--chunk-size", "1")

    assert code == 0
    assert (report["dates"][0]["done"], report["dates"][0]["pending"]) == (1, 1)
    assert "model overloaded" in report["failures"][0]
    assert not (clone / ".cache" / "summaries" / "LOCK").exists()


def test_run_local_respects_another_runs_lock(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})
    lock = clone / ".cache" / "summaries" / "LOCK"
    lock.parent.mkdir(parents=True)
    lock.write_text("12345 another run\n")
    calls = []

    code, report = run_local(clone, monkeypatch, capsys, fake_client(calls), "--client", "codex")

    assert code == 3 and report["locked"] is True and calls == []
    assert lock.exists()


def scripted_client(calls, outputs):
    """A coding agent whose n-th call writes outputs[n](ids) to the output file (the last one repeats)."""

    def run(argv, cwd, capture_output, text, timeout, stdin):
        calls.append(argv)
        prompt = next(a for a in argv if "Input file:" in a)
        source = re.search(r"Input file: (\S+?)\.(?:\s|$)", prompt).group(1)
        target = re.search(r"Output file: (\S+?)\.(?:\s|$)", prompt).group(1)
        ids = re.findall(r"^=== (\S+)$", Path(source).read_text(), flags=re.MULTILINE)
        Path(target).write_text(outputs[min(len(calls), len(outputs)) - 1](ids))
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    return run


def complete(ids):
    return "".join(f"=== {i}\n{FIELDS}\n" for i in ids)


def first_lacks_a_field(ids):
    """Every block complete except the first one's, which has no conclusion."""
    return complete(ids).replace("conclusion: c\n", "", 1)


def test_a_chunk_with_fewer_complete_blocks_than_papers_is_retried_once(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    calls = []

    code, report = run_local(clone, monkeypatch, capsys, scripted_client(calls, [first_lacks_a_field, complete]), "--client", "claude")

    assert code == 0 and len(calls) == 2
    assert report["failures"] == []
    assert (report["dates"][0]["done"], report["dates"][0]["pending"]) == (2, 0)
    log = parse_jsonl(git(remote, "show", "data:logs/summary-runs.jsonl"))[-1]
    assert log["reason"] == "1 chunks, 0 failed"


def test_a_chunk_still_short_after_its_retry_counts_as_failed_with_the_counts(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2"), paper("3")])})
    calls = []

    code, report = run_local(clone, monkeypatch, capsys, scripted_client(calls, [first_lacks_a_field]), "--client", "claude")

    assert code == 0 and len(calls) == 2
    [failure] = report["failures"]
    assert failure.startswith("chunk-000.in.txt:") and "2 of 3 papers" in failure
    assert (report["dates"][0]["done"], report["dates"][0]["pending"]) == (2, 1)
    log = parse_jsonl(git(remote, "show", "data:logs/summary-runs.jsonl"))[-1]
    assert log["reason"] == "1 chunks, 1 failed"


def test_a_retry_keeps_the_blocks_the_first_attempt_got_right(tmp_path, remote_and_clone, monkeypatch, capsys):
    """The first attempt lacks paper 1's conclusion, the retry paper 2's: together they cover both."""
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})

    def second_lacks_a_field(ids):
        return complete(ids[:1]) + first_lacks_a_field(ids[1:])

    _, report = run_local(clone, monkeypatch, capsys, scripted_client([], [first_lacks_a_field, second_lacks_a_field]), "--client", "claude")

    assert report["failures"] == []
    assert [r["id"] for r in parse_jsonl(git(remote, "show", f"data:{AI_FILE}"))] == ["1", "2"]


def test_chunk_prompt_lets_a_client_without_file_tools_use_the_shell_for_the_two_files():
    """Codex 0.166 reads and writes files only through shell commands; told not to run any, it gave up (2026-11-13)."""
    prompt = chunk_prompt("/r/INSTRUCTIONS.md", "/r/chunk-000.in.txt", "/r/chunk-000.out.txt")
    assert "do not run shell commands" not in prompt
    assert "shell commands only to read those two files and to write the output file" in prompt
    assert "do not edit anything else" in prompt


def test_antigravity_works_in_the_day_folder_so_its_approved_edits_cannot_reach_the_repository(tmp_path, remote_and_clone, monkeypatch, capsys):
    """accept-edits approves edits inside agy's workspace (its working folder); outside it a headless run refuses."""
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    calls, cwds = [], []

    code, report = run_local(clone, monkeypatch, capsys, fake_client(calls, cwds=cwds), "--client", "antigravity")

    day_folder = (clone / ".cache" / "summaries" / DAY).resolve()
    assert code == 0 and report["failures"] == [] and cwds == [str(day_folder)]
    prompt = calls[0][2]
    for name in ("INSTRUCTIONS.md", "chunk-000.in.txt", "chunk-000.out.txt"):
        assert str(day_folder / name) in prompt


def test_other_clients_still_work_in_the_repository(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})
    cwds = []

    run_local(clone, monkeypatch, capsys, fake_client([], cwds=cwds), "--client", "codex")

    assert cwds == [str(clone)]


def test_a_client_that_cannot_start_is_a_chunk_failure_not_a_crash(tmp_path, remote_and_clone, monkeypatch, capsys):
    """agy missing from the scheduled task's PATH: the run still prints its JSON, so the task can fall back."""
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})

    def missing(argv, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    code, report = run_local(clone, monkeypatch, capsys, missing, "--client", "antigravity")

    assert code == 0 and len(report["failures"]) == 1
    assert "cannot run agy" in report["failures"][0]
