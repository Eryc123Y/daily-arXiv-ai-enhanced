import json
import subprocess
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

    code, _out = run(clone, "ingest", "--date", DAY, "--input", str(crawl), capsys=capsys)

    assert code == 0
    assert [p["id"] for p in parse_jsonl(branch_file(remote, f"data/{DAY}.jsonl"))] == ["B", "C"]
    assert "has_new_content=true" in gh_output.read_text()
    assert f"{DAY}.jsonl" in branch_file(remote, "assets/file-list.txt")
    [entry] = parse_jsonl(branch_file(remote, "logs/summary-runs.jsonl"))
    assert (entry["date"], entry["path"], entry["added"], entry["total"]) == (DAY, "crawl", 2, 2)
    assert entry["at"].endswith("+00:00")


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

    _code, out = run(clone, "prepare", "--date", DAY, capsys=capsys)

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

    _code, out = run(clone, "status", "--days", "36500", capsys=capsys)

    dates = {d["date"]: d for d in json.loads(out)["dates"]}
    assert dates[DAY] == {"date": DAY, "total": 2, "done": 1, "pending": 1}


def test_mode_command_writes_the_decision_for_the_workflow(tmp_path, remote_and_clone, monkeypatch, capsys):
    _, clone = remote_and_clone
    gh_output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output))
    monkeypatch.setenv("SUMMARY_MODE", "api")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    _code, out = run(clone, "mode", capsys=capsys)

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

    code, _out = run(clone, "api", "--days", "36500", capsys=capsys)

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

    with pytest.raises(subprocess.CalledProcessError):
        run(clone, "prepare", "--date", DAY, capsys=capsys)

    assert not (clone / ".cache" / "summaries" / "LOCK").exists()


def log_lines(remote):
    return parse_jsonl(git(remote, "show", "data:logs/summary-runs.jsonl"))


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


@pytest.fixture
def pipeline(tmp_path, remote_and_clone, monkeypatch):
    """ensure-day with today 2026-11-09 and both crawls stubbed; GitHub must not be called.

    state.today: papers today's /new crawl returns (or an exception to raise);
    state.recent: day -> papers on the /recent listing; state.covered: its days.
    """
    from summaries import cli, github, localcrawl

    remote, clone = remote_and_clone
    state = SimpleNamespace(
        remote=remote, clone=clone, today="2026-11-09", crawls=[], wanted=[],
        new=[paper("A"), paper("B"), paper("C")], recent={}, covered=[], recent_error=None,
    )

    def seed(files):
        seed_data_branch(tmp_path, remote, {f"data/{d}.jsonl": dump_jsonl(rows) for d, rows in files.items()})

    def crawl(repo_dir, slug):
        state.crawls.append((Path(repo_dir), slug))
        if isinstance(state.new, Exception):
            raise state.new
        return state.new

    def recent(repo_dir, slug, wanted):
        state.wanted.append(list(wanted))
        if state.recent_error:
            raise state.recent_error
        days = {d: state.recent[d] for d in wanted if d in state.recent}
        return localcrawl.Listing(days=days, covered=sorted(state.covered or state.recent))

    monkeypatch.setattr(github, "gh", lambda *args: pytest.fail(f"GitHub was called: {args}"))
    monkeypatch.delenv("FEED_COMMAND", raising=False)  # a machine with the feed set up must not run it here
    monkeypatch.setattr(cli, "utc_today", lambda: state.today)
    monkeypatch.setattr(localcrawl, "crawl", crawl)
    monkeypatch.setattr(localcrawl, "recent", recent)
    state.seed = seed
    state.run = lambda *argv, capsys: run(clone, "ensure-day", *argv, capsys=capsys)
    return state


def ids_on(remote, day):
    return [p["id"] for p in parse_jsonl(branch_file(remote, f"data/{day}.jsonl"))]


def test_ensure_day_does_nothing_when_the_day_is_published(tmp_path, pipeline, capsys):
    from summaries.datafiles import venue_days_file, venue_settings

    files = {f"data/{d}.jsonl": dump_jsonl([paper(i)]) for d, i in (("2026-11-06", "A"), ("2026-11-09", "B"))}
    listing = {"assets/file-list.txt": "2026-11-06.jsonl\n2026-11-09.jsonl\n"}
    seed_data_branch(tmp_path, pipeline.remote, {**files, **listing, **venue_settings(), **venue_days_file({})})

    code, out = pipeline.run(capsys=capsys)

    # "feed": ensure-day says the feed was skipped when FEED_COMMAND is unset (spec S1, R5).
    assert code == 0 and json.loads(out) == {"date": "2026-11-09", "status": "present", "total": 1, "feed": "skipped"}
    assert pipeline.crawls == [] and pipeline.wanted == []


def test_ensure_day_skips_weekends(pipeline, capsys):
    pipeline.seed({"2026-11-06": [paper("A")]})
    pipeline.today = "2026-11-08"

    _code, out = pipeline.run(capsys=capsys)

    assert json.loads(out)["status"] == "weekend" and pipeline.crawls == []


def test_ensure_day_crawls_today_on_this_machine(pipeline, capsys):
    pipeline.seed({"2026-11-06": [paper("A")]})

    code, out = pipeline.run(capsys=capsys)

    report = json.loads(out)
    assert code == 0
    assert (report["status"], report["added"], report["total"]) == ("present", 2, 2)
    assert pipeline.crawls == [(pipeline.clone, "alice/my-arxiv")]
    assert ids_on(pipeline.remote, "2026-11-09") == ["B", "C"]
    entry = parse_jsonl(branch_file(pipeline.remote, "logs/summary-runs.jsonl"))[-1]
    assert (entry["date"], entry["path"], entry["added"]) == ("2026-11-09", "crawl", 2)


def test_ensure_day_before_the_announcement_reports_missing(pipeline, capsys):
    """/new still shows Friday's papers: all seen already, nothing published."""
    pipeline.seed({"2026-11-06": [paper("A")]})
    pipeline.new = [paper("A")]

    code, out = pipeline.run(capsys=capsys)

    assert code == 0 and (json.loads(out)["status"], json.loads(out)["added"]) == ("missing", 0)


def test_ensure_day_reports_a_failed_crawl(pipeline, capsys):
    from summaries import localcrawl

    pipeline.seed({"2026-11-06": [paper("A")]})
    pipeline.new = localcrawl.CrawlError("the crawl returned no papers; arXiv may be unreachable")

    code, out = pipeline.run(capsys=capsys)

    report = json.loads(out)
    assert code == 1 and report["status"] == "error" and "arXiv may be unreachable" in report["reason"]


def test_ensure_day_backfills_missed_days_from_the_recent_listing(pipeline, capsys):
    pipeline.seed({"2026-11-04": [paper("A")]})
    pipeline.recent = {"2026-11-05": [paper("A"), paper("D"), paper("E")], "2026-11-06": [paper("F")], "2026-11-09": [paper("B")]}
    pipeline.new = [paper("B")]

    code, out = pipeline.run(capsys=capsys)

    report = json.loads(out)
    assert code == 0 and report["status"] == "present"
    assert report["backfilled"] == {"2026-11-05": 2, "2026-11-06": 1} and report["gap"] == []
    assert pipeline.wanted == [["2026-11-05", "2026-11-06"]]
    assert ids_on(pipeline.remote, "2026-11-05") == ["D", "E"]
    assert ids_on(pipeline.remote, "2026-11-06") == ["F"]
    assert ids_on(pipeline.remote, "2026-11-09") == ["B"]


def test_ensure_day_reports_days_older_than_the_listing_as_a_gap(pipeline, capsys):
    """The listing covers five announcements; 11-04 had none (a holiday) and is neither backfilled nor a gap."""
    pipeline.seed({"2026-10-22": [paper("A")]})
    pipeline.recent = {d: [paper(d)] for d in ("2026-11-02", "2026-11-03", "2026-11-05", "2026-11-06", "2026-11-09")}

    code, out = pipeline.run(capsys=capsys)

    report = json.loads(out)
    assert code == 0 and report["status"] == "present"
    assert sorted(report["backfilled"]) == ["2026-11-02", "2026-11-03", "2026-11-05", "2026-11-06"]
    assert report["gap"] == ["2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]


def test_ensure_day_still_crawls_today_when_the_backfill_fails(pipeline, capsys):
    from summaries import localcrawl

    pipeline.seed({"2026-11-04": [paper("A")]})
    pipeline.recent_error = localcrawl.CrawlError("the arXiv API did not answer: timed out")

    code, out = pipeline.run(capsys=capsys)

    report = json.loads(out)
    assert code == 0 and report["status"] == "present"
    assert "timed out" in report["backfill_error"]
    assert report["gap"] == ["2026-11-05", "2026-11-06"]


def test_ensure_day_for_a_past_day_uses_the_recent_listing(pipeline, capsys):
    pipeline.seed({"2026-11-05": [paper("A")], "2026-11-09": [paper("B")]})
    pipeline.recent = {"2026-11-06": [paper("F")]}

    code, out = pipeline.run("--date", "2026-11-06", capsys=capsys)

    report = json.loads(out)
    assert code == 0 and (report["status"], report["total"]) == ("present", 1)
    assert pipeline.crawls == [] and ids_on(pipeline.remote, "2026-11-06") == ["F"]


AI = {k: f"{k}内容" for k in ("tldr", "motivation", "method", "result", "conclusion")}


@pytest.fixture
def handover_day(tmp_path, remote_and_clone, monkeypatch, capsys):
    """Two papers, one summarised by a subagent chunk; no provider settings or keys; GitHub must not be called."""
    from summaries import github

    remote, clone = remote_and_clone
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1"), paper("2")])})
    run(clone, "prepare", "--date", DAY, capsys=capsys)
    (clone / ".cache" / "summaries" / DAY / "chunk-000.out.txt").write_text("=== 1\n" + FIELDS.format(n=1))
    for name in ("SUMMARY_PROVIDER", "SUMMARY_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(github, "gh", lambda *args: pytest.fail(f"GitHub was called: {args}"))
    return remote, clone


def test_handover_summarises_the_rest_through_the_api_here_when_a_key_is_set(handover_day, monkeypatch, capsys):
    remote, clone = handover_day
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(AI))]
    )
    monkeypatch.setattr(anthropic_api, "make_client", lambda api_key=None: client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    code, out = run(clone, "handover", "--date", DAY, "--reason", "weekly 81%", capsys=capsys)

    result = json.loads(out)
    assert code == 0 and result["path"] == "api-fallback"
    assert [r["id"] for r in parse_jsonl(branch_file(remote, AI_FILE))] == ["1", "2"]
    entry = log_lines(remote)[-1]
    assert (entry["date"], entry["path"], entry["done"], entry["pending"]) == (DAY, "api-fallback", 2, 0)
    assert entry["reason"] == "weekly 81%"


def test_handover_without_a_key_pauses_and_logs_why(handover_day, capsys):
    remote, clone = handover_day

    code, out = run(clone, "handover", "--date", DAY, "--reason", "weekly 81%", capsys=capsys)

    assert code == 0 and json.loads(out)["path"] == "paused-no-key"
    entry = log_lines(remote)[-1]
    assert (entry["path"], entry["done"], entry["pending"]) == ("paused-no-key", 1, 1)
    assert entry["reason"].startswith("weekly 81%; ") and "ANTHROPIC_API_KEY" in entry["reason"]


def test_handover_checks_the_configured_provider_and_model(handover_day, monkeypatch, capsys):
    remote, clone = handover_day
    monkeypatch.setenv("SUMMARY_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "x")

    _, out = run(clone, "handover", "--date", DAY, capsys=capsys)

    assert json.loads(out)["path"] == "paused-no-key"
    assert "SUMMARY_MODEL" in log_lines(remote)[-1]["reason"]


def test_handover_with_nothing_pending_needs_no_fallback(tmp_path, remote_and_clone, monkeypatch, capsys):
    from summaries import github

    remote, clone = remote_and_clone
    ai = [{**paper("1"), "AI": AI}]
    seed_data_branch(tmp_path, remote, {f"data/{DAY}.jsonl": dump_jsonl([paper("1")]), AI_FILE: dump_jsonl(ai)})
    monkeypatch.setattr(github, "gh", lambda *args: pytest.fail(f"GitHub was called: {args}"))

    _, out = run(clone, "handover", "--date", DAY, capsys=capsys)

    assert json.loads(out)["path"] == "claude-code"
