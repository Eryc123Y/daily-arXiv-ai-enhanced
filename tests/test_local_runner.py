import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import git, seed_data_branch

from summaries.cli import main
from summaries.local_runner import chunk_prompt, client_argv
from summaries.records import dump_jsonl, parse_jsonl

DAY = "2026-10-30"
AI_FILE = f"data/{DAY}_AI_enhanced_English.jsonl"
PROMPT = "Read /r/INSTRUCTIONS.md and follow it exactly."


def paper(paper_id):
    return {"id": paper_id, "categories": ["cs.CV"], "title": f"T{paper_id}", "authors": ["A"], "summary": f"S{paper_id}"}


def test_claude_runs_headless_with_haiku_and_only_file_tools():
    assert client_argv("claude", PROMPT) == ["claude", "-p", PROMPT, "--model", "haiku", "--allowedTools", "Read,Write"]
    assert client_argv("claude", PROMPT, model="sonnet")[4] == "sonnet"


def test_codex_runs_exec_in_a_workspace_write_sandbox():
    assert client_argv("codex", PROMPT) == ["codex", "exec", "--sandbox", "workspace-write", PROMPT]
    assert client_argv("codex", PROMPT, model="m") == ["codex", "exec", "--sandbox", "workspace-write", "-m", "m", PROMPT]


def test_antigravity_runs_its_cli_headless():
    assert client_argv("antigravity", PROMPT) == ["agy", "-p", PROMPT]
    assert client_argv("antigravity", PROMPT, model="m") == ["agy", "-p", PROMPT, "--model", "m"]


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


def fake_client(calls, fail=()):
    """Acts like a coding agent: reads the chunk named in the prompt and writes blocks."""

    def run(argv, cwd, capture_output, text, timeout):
        calls.append(argv)
        prompt = next(a for a in argv if "Input file:" in a)
        source = re.search(r"Input file: (\S+?)\.(?:\s|$)", prompt).group(1)
        target = re.search(r"Output file: (\S+?)\.(?:\s|$)", prompt).group(1)
        ids = re.findall(r"^=== (\S+)$", Path(source).read_text(), flags=re.M)
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
