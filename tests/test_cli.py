import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from conftest import git, seed_data_branch

from summaries import anthropic_api
from summaries.cli import main
from summaries.records import dump_jsonl, parse_jsonl

DAY = "2026-10-30"


@pytest.fixture(autouse=True)
def data_repo(monkeypatch):
    monkeypatch.setenv("DATA_REPO", "alice/my-arxiv")
AI_FILE = f"data/{DAY}_AI_enhanced_English.jsonl"
FIELDS = "tldr: 总结{n}\nmotivation: 动机\nmethod: 方法\nresult: 结果\nconclusion: 结论\n"


def paper(paper_id):
    return {"id": paper_id, "categories": ["cs.CV"], "title": f"T{paper_id}", "authors": ["A"], "summary": f"S{paper_id}"}


def run(clone, *argv, env=None, monkeypatch=None, capsys=None):
    code = main(["--repo", str(clone), "--work-dir", str(clone / ".cache" / "summaries"), *argv])
    output = capsys.readouterr().out if capsys else ""
    return code, output


def branch_file(remote, path):
    return git(remote, "show", f"data:{path}")


def test_ingest_publishes_only_papers_not_seen_in_the_last_week(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {"data/2026-10-29.jsonl": dump_jsonl([paper("A")])})
    crawl = tmp_path / "crawl.jsonl"
    crawl.write_text(dump_jsonl([paper("A"), paper("B"), paper("B"), paper("C")]))
    gh_output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))

    code, out = run(clone, "ingest", "--date", DAY, "--input", str(crawl), capsys=capsys)

    assert code == 0
    assert [p["id"] for p in parse_jsonl(branch_file(remote, f"data/{DAY}.jsonl"))] == ["B", "C"]
    assert "has_new_content=true" in gh_output.read_text()
    assert f"{DAY}.jsonl" in branch_file(remote, "assets/file-list.txt")


def test_ingest_on_a_day_without_an_announcement_publishes_nothing(tmp_path, remote_and_clone, monkeypatch, capsys):
    """Weekend runs see Friday's listing again: every paper is already published."""
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {"data/2026-10-30.jsonl": dump_jsonl([paper("A"), paper("B")])})
    head = git(remote, "rev-parse", "data")
    crawl = tmp_path / "crawl.jsonl"
    crawl.write_text(dump_jsonl([paper("B"), paper("A")]))
    gh_output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))

    run(clone, "ingest", "--date", "2026-10-31", "--input", str(crawl), capsys=capsys)

    assert "has_new_content=false" in gh_output.read_text()
    assert git(remote, "rev-parse", "data") == head


def test_ingest_rerun_on_the_same_day_adds_late_papers_without_dropping_any(tmp_path, remote_and_clone, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("A")])})
    crawl = tmp_path / "crawl.jsonl"
    crawl.write_text(dump_jsonl([paper("B")]))

    run(clone, "ingest", "--date", DAY, "--input", str(crawl), capsys=capsys)

    assert [p["id"] for p in parse_jsonl(branch_file(remote, f"data/{DAY}.jsonl"))] == ["A", "B"]


def test_claude_code_flow_prepare_merge_and_resume(tmp_path, remote_and_clone, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2"), paper("3")])})

    code, out = run(clone, "prepare", "--date", DAY, "--chunk-size", "2", capsys=capsys)
    plan = json.loads(out)
    assert code == 0
    assert (plan["total"], plan["pending"], len(plan["chunks"])) == (3, 3, 2)
    first = Path(plan["chunks"][0]["input"]).read_text()
    assert "=== 1" in first and "=== 2" in first and "abstract: S1" in first
    assert "English" in Path(plan["instructions"]).read_text()

    # Subagent finished chunk 0 only; one block is unusable and one id is foreign.
    Path(plan["chunks"][0]["output"]).write_text(
        "=== 1\n" + FIELDS.format(n=1) + "\n=== 2\ntldr: only one field\n\n=== 999\n" + FIELDS.format(n=9)
    )
    code, out = run(clone, "merge", "--date", DAY, capsys=capsys)
    merged = json.loads(out)
    assert (merged["done"], merged["pending"]) == (1, 2)
    assert any("999" in p for p in merged["problems"])
    assert any(p.endswith("2: incomplete block") for p in merged["problems"])
    assert [r["id"] for r in parse_jsonl(branch_file(remote, AI_FILE))] == ["1"]
    assert parse_jsonl(branch_file(remote, AI_FILE))[0]["AI"]["tldr"] == "总结1"

    # A second prepare while the first run holds the lock is refused.
    code, out = run(clone, "prepare", "--date", DAY, capsys=capsys)
    assert code == 3 and json.loads(out)["locked"] is True

    # Next run resumes with the two papers still pending.
    run(clone, "finish", capsys=capsys)
    code, out = run(clone, "prepare", "--date", DAY, "--chunk-size", "20", capsys=capsys)
    resumed = json.loads(out)
    assert (resumed["done"], resumed["pending"], len(resumed["chunks"])) == (1, 2, 1)
    assert "=== 1\n" not in Path(resumed["chunks"][0]["input"]).read_text()


def test_prepare_merges_outputs_left_by_an_interrupted_run(tmp_path, remote_and_clone, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    run(clone, "prepare", "--date", DAY, capsys=capsys)
    work = clone / ".cache" / "summaries" / DAY
    (work / "chunk-000.out.txt").write_text("=== 2\n" + FIELDS.format(n=2))
    run(clone, "finish", capsys=capsys)

    code, out = run(clone, "prepare", "--date", DAY, capsys=capsys)

    plan = json.loads(out)
    assert plan["merged_leftovers"]["done"] == 1
    assert (plan["done"], plan["pending"]) == (1, 1)
    assert [r["id"] for r in parse_jsonl(branch_file(remote, AI_FILE))] == ["2"]


def test_status_reports_progress_for_recent_days(tmp_path, remote_and_clone, capsys, monkeypatch):
    remote, clone = remote_and_clone
    ai = [{**paper("1"), "AI": {k: "x" for k in ("tldr", "motivation", "method", "result", "conclusion")}}]
    seed_data_branch(
        tmp_path,
        remote,
        {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")]), AI_FILE: dump_jsonl(ai), "data/2026-09-07.jsonl": "{}\n"},
    )

    code, out = run(clone, "status", "--days", "36500", capsys=capsys)

    dates = {d["date"]: d for d in json.loads(out)["dates"]}
    assert dates[DAY] == {"date": DAY, "total": 2, "done": 1, "pending": 1}


def test_mode_command_writes_the_decision_for_the_workflow(tmp_path, remote_and_clone, monkeypatch, capsys):
    _, clone = remote_and_clone
    gh_output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))
    monkeypatch.setenv("SUMMARY_MODE", "api")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    code, out = run(clone, "mode", capsys=capsys)

    assert "mode=claude-code" in gh_output.read_text()
    assert "::warning::" in out


def test_api_command_publishes_summaries_and_leaves_failures_pending(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    ai = {k: f"{k}内容" for k in ("tldr", "motivation", "method", "result", "conclusion")}

    def create(**request):
        if "S2" in request["messages"][0]["content"]:
            return SimpleNamespace(stop_reason="refusal", content=[])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(ai))])

    client = MagicMock()
    client.messages.create.side_effect = create
    monkeypatch.setattr(anthropic_api, "make_client", lambda api_key=None: client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    code, out = run(clone, "api", "--date", DAY, capsys=capsys)

    assert code == 0
    assert "::warning::2 left pending: refusal" in out
    records = parse_jsonl(branch_file(remote, AI_FILE))
    assert [r["id"] for r in records] == ["1"]
    assert records[0]["AI"] == ai


def test_api_without_a_date_fills_pending_papers_of_recent_days(tmp_path, remote_and_clone, monkeypatch, capsys):
    """A weekend run has no new file but can still finish Friday's leftovers."""
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})
    ai = {k: "内容" for k in ("tldr", "motivation", "method", "result", "conclusion")}
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(ai))]
    )
    monkeypatch.setattr(anthropic_api, "make_client", lambda api_key=None: client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    code, out = run(clone, "api", "--days", "36500", capsys=capsys)

    assert code == 0
    assert [r["id"] for r in parse_jsonl(branch_file(remote, AI_FILE))] == ["1"]


def test_api_exits_non_zero_when_every_paper_fails(tmp_path, remote_and_clone, monkeypatch, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(stop_reason="refusal", content=[])
    monkeypatch.setattr(anthropic_api, "make_client", lambda api_key=None: client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    code, _ = run(clone, "api", "--date", DAY, capsys=capsys)

    assert code == 1


def test_api_publishes_each_batch_before_a_fatal_error(tmp_path, remote_and_clone, monkeypatch, capsys):
    import anthropic
    import httpx2
    import pytest

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    ai = {k: "内容" for k in ("tldr", "motivation", "method", "result", "conclusion")}
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def create(**kwargs):
        if "S2" in kwargs["messages"][0]["content"]:
            raise anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=request), body=None)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(ai))])

    client = MagicMock()
    client.messages.create.side_effect = create
    monkeypatch.setattr(anthropic_api, "make_client", lambda api_key=None: client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with pytest.raises(anthropic.AuthenticationError):
        run(clone, "api", "--date", DAY, "--batch-size", "1", capsys=capsys)

    assert [r["id"] for r in parse_jsonl(branch_file(remote, AI_FILE))] == ["1"]


def test_prepare_releases_the_lock_when_it_fails(tmp_path, remote_and_clone, capsys):
    import pytest

    _, clone = remote_and_clone
    git(clone, "remote", "set-url", "origin", str(tmp_path / "unreachable.git"))

    with pytest.raises(Exception):
        run(clone, "prepare", "--date", DAY, capsys=capsys)

    assert not (clone / ".cache" / "summaries" / "LOCK").exists()


def fake_gh(secrets, calls, variables=None):
    """Stand-in for the gh CLI: lists `secrets`, reads `variables`, records dispatches."""
    import subprocess

    def gh(*args):
        calls.append(args)
        if args[:2] == ("secret", "list"):
            return json.dumps([{"name": n} for n in secrets])
        if args[:2] == ("variable", "get"):
            if variables == "unreachable":
                raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 502: Bad Gateway")
            if args[2] not in (variables or {}):
                raise subprocess.CalledProcessError(1, ["gh", *args], stderr=f"variable {args[2]} was not found")
            return variables[args[2]] + "\n"
        return ""

    return gh


def log_lines(remote):
    return parse_jsonl(git(remote, "show", "data:logs/summary-runs.jsonl"))


def test_handover_dispatches_the_api_job_when_the_secret_exists(tmp_path, remote_and_clone, monkeypatch, capsys):
    from summaries import cli

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    run(clone, "prepare", "--date", DAY, capsys=capsys)
    (clone / ".cache" / "summaries" / DAY / "chunk-000.out.txt").write_text("=== 1\n" + FIELDS.format(n=1))
    calls = []
    monkeypatch.setattr(cli, "gh", fake_gh(["ANTHROPIC_API_KEY"], calls))

    code, out = run(clone, "handover", "--date", DAY, "--reason", "weekly 81%", capsys=capsys)

    result = json.loads(out)
    assert code == 0
    assert result["path"] == "api-fallback" and result["pending"] == 1
    assert ("workflow", "run", "summarize-api.yml", "-R", "alice/my-arxiv", "-f", f"date={DAY}") in calls
    assert [r["id"] for r in parse_jsonl(branch_file(remote, AI_FILE))] == ["1"]
    entry = log_lines(remote)[-1]
    assert (entry["date"], entry["path"], entry["done"], entry["pending"]) == (DAY, "api-fallback", 1, 1)
    assert entry["reason"] == "weekly 81%"


def test_handover_without_a_key_pauses_and_logs_it(tmp_path, remote_and_clone, monkeypatch, capsys):
    from summaries import cli

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})
    calls = []
    monkeypatch.setattr(cli, "gh", fake_gh([], calls))

    code, out = run(clone, "handover", "--date", DAY, capsys=capsys)

    assert json.loads(out)["path"] == "paused-no-key"
    assert not any(c[:2] == ("workflow", "run") for c in calls)
    assert log_lines(remote)[-1]["path"] == "paused-no-key"


def test_handover_with_nothing_pending_needs_no_fallback(tmp_path, remote_and_clone, monkeypatch, capsys):
    from summaries import cli

    remote, clone = remote_and_clone
    ai = [{**paper("1"), "AI": {k: "x" for k in ("tldr", "motivation", "method", "result", "conclusion")}}]
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")]), AI_FILE: dump_jsonl(ai)})
    calls = []
    monkeypatch.setattr(cli, "gh", fake_gh(["ANTHROPIC_API_KEY"], calls))

    _, out = run(clone, "handover", "--date", DAY, capsys=capsys)

    assert json.loads(out)["path"] == "claude-code"
    assert calls == []


def test_record_appends_the_day_path_to_the_run_log(tmp_path, remote_and_clone, capsys):
    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})

    run(clone, "record", "--date", DAY, "--path", "claude-code", capsys=capsys)
    run(clone, "record", "--date", DAY, "--path", "api-fallback", capsys=capsys)

    entries = log_lines(remote)
    assert [e["path"] for e in entries] == ["claude-code", "api-fallback"]
    assert entries[0]["total"] == 1 and "at" in entries[0]
    assert "summary-runs" not in branch_file(remote, "assets/file-list.txt")



def test_api_command_works_with_an_openai_compatible_provider(tmp_path, remote_and_clone, monkeypatch, capsys):
    from summaries import openai_compat

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})
    ai = {k: f"{k} text" for k in ("tldr", "motivation", "method", "result", "conclusion")}
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(ai), refusal=None), finish_reason="stop")]
    )
    seen = {}

    def make_client(api_key, base_url=None):
        seen.update(api_key=api_key, base_url=base_url)
        return client

    monkeypatch.setattr(openai_compat, "make_client", make_client)
    for name, value in {"SUMMARY_PROVIDER": "gemini", "SUMMARY_MODEL": "gemini-test", "GEMINI_API_KEY": "g-key"}.items():
        monkeypatch.setenv(name, value)

    code, _ = run(clone, "api", "--date", DAY, capsys=capsys)

    assert code == 0
    assert seen == {"api_key": "g-key", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"}
    assert client.chat.completions.create.call_args.kwargs["model"] == "gemini-test"
    assert parse_jsonl(branch_file(remote, AI_FILE))[0]["AI"] == ai


def test_api_command_refuses_to_start_without_a_ready_provider(tmp_path, remote_and_clone, monkeypatch, capsys):
    _, clone = remote_and_clone
    monkeypatch.setenv("SUMMARY_PROVIDER", "openai")
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)

    code, out = run(clone, "api", "--date", DAY, capsys=capsys)

    assert code == 2
    assert "SUMMARY_MODEL" in out


def test_mode_command_accepts_a_ready_gemini_provider(tmp_path, remote_and_clone, monkeypatch, capsys):
    _, clone = remote_and_clone
    gh_output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))
    for name, value in {"SUMMARY_MODE": "api", "SUMMARY_PROVIDER": "gemini", "SUMMARY_MODEL": "g", "GEMINI_API_KEY": "x"}.items():
        monkeypatch.setenv(name, value)

    run(clone, "mode", capsys=capsys)

    assert "mode=api" in gh_output.read_text()


def test_handover_checks_the_configured_providers_secret_and_model(tmp_path, remote_and_clone, monkeypatch, capsys):
    from summaries import cli

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})
    calls = []
    monkeypatch.setattr(cli, "gh", fake_gh(["GEMINI_API_KEY"], calls, {"SUMMARY_PROVIDER": "gemini"}))

    _, out = run(clone, "handover", "--date", DAY, capsys=capsys)
    assert json.loads(out)["path"] == "paused-no-key"
    assert "SUMMARY_MODEL" in log_lines(remote)[-1]["reason"]

    monkeypatch.setattr(cli, "gh", fake_gh(["GEMINI_API_KEY"], calls, {"SUMMARY_PROVIDER": "gemini", "SUMMARY_MODEL": "g"}))
    _, out = run(clone, "handover", "--date", DAY, capsys=capsys)
    assert json.loads(out)["path"] == "api-fallback"



def test_handover_pauses_when_the_repository_settings_cannot_be_read(tmp_path, remote_and_clone, monkeypatch, capsys):
    """A failed gh call must not be mistaken for an unset SUMMARY_PROVIDER."""
    from summaries import cli

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")])})
    calls = []
    monkeypatch.setattr(cli, "gh", fake_gh(["ANTHROPIC_API_KEY"], calls, "unreachable"))

    _, out = run(clone, "handover", "--date", DAY, capsys=capsys)

    assert json.loads(out)["path"] == "paused-no-key"
    assert "could not read" in log_lines(remote)[-1]["reason"]
    assert not any(c[:2] == ("workflow", "run") for c in calls)
