"""digest --client: the writer's command line per client, and how the prompt reaches it."""

import json
import subprocess

import pytest

from summaries import digest, weekly
from summaries.cli import main


def parse(*extra):
    from summaries.cli import build_parser

    return build_parser().parse_args(["digest", "--dir", "v", *extra])


def test_the_default_client_is_claude_with_sonnet_and_a_codex_fallback():
    args = parse()
    assert digest.clients(args) == [
        ["claude", "-p", "--model", "sonnet", "--tools", "", "--strict-mcp-config"],
        digest.FALLBACK_COMMAND,
    ]


def test_client_claude_takes_a_model():
    assert digest.clients(parse("--client", "claude", "--model", "opus"))[0][3] == "opus"


def test_client_codex_has_no_second_codex_fallback():
    argvs = digest.clients(parse("--client", "codex"))
    assert argvs == [digest.FALLBACK_COMMAND]
    assert digest.clients(parse("--client", "codex", "--model", "m"))[0][-3:] == ["-m", "m", "-"]


def test_client_antigravity_sends_the_prompt_as_the_value_of_p_and_falls_back_to_codex():
    primary, fallback = digest.clients(parse("--client", "antigravity"))
    assert primary[:3] == ["agy", "-p", digest.PROMPT_ARG]
    assert {"--sandbox", "--disable-slash-commands"} <= set(primary)
    settings = json.loads(primary[primary.index("--settings") + 1])
    # Default mode and strict review, plus deny rules for every tool kind: the writer needs no tools at all.
    assert settings["agentMode"] == "" and settings["toolPermission"] == "strict"
    assert {"command(*)", "unsandboxed(*)", "mcp(*)", "read_url(*)", "execute_url(*)", "read_file(/)", "write_file(/)"} <= set(settings["permissions"]["deny"])
    assert "--dangerously-skip-permissions" not in primary
    assert "--model" not in primary  # the Claude default "sonnet" is not an agy model
    assert fallback == digest.FALLBACK_COMMAND
    assert digest.clients(parse("--client", "antigravity", "--model", "g"))[0][-2:] == ["--model", "g"]


def test_command_still_overrides_and_cannot_be_combined_with_client(capsys):
    assert digest.clients(parse("--command", '["mycli", "{model}"]')) == [["mycli", "sonnet"]]
    with pytest.raises(SystemExit):
        parse("--client", "codex", "--command", '["mycli"]')
    assert "--client" in capsys.readouterr().err


def test_an_explicit_fallback_is_kept_for_another_client():
    assert digest.clients(parse("--client", "antigravity", "--fallback", '["other"]'))[1] == ["other"]
    assert digest.clients(parse("--client", "antigravity", "--fallback", "")) == [digest.clients(parse("--client", "antigravity"))[0]]


class Recorder:
    def __init__(self, returncode=0, stdout="answer"):
        self.calls = []
        self.result = subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="err line")

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.result


def test_a_prompt_placeholder_puts_the_prompt_in_the_arguments_and_closes_stdin(monkeypatch):
    run = Recorder()
    monkeypatch.setattr(digest.subprocess, "run", run)

    assert digest.run_model(["agy", "-p", digest.PROMPT_ARG, "--sandbox"], "the prompt", "/repo") == "answer"

    argv, kwargs = run.calls[0]
    assert argv == ["agy", "-p", "the prompt", "--sandbox"]
    assert kwargs["stdin"] is subprocess.DEVNULL and kwargs["input"] is None


def test_without_the_placeholder_the_prompt_goes_on_stdin(monkeypatch):
    run = Recorder()
    monkeypatch.setattr(digest.subprocess, "run", run)

    digest.run_model(["codex", "exec", "-"], "the prompt", "/repo")

    argv, kwargs = run.calls[0]
    assert argv == ["codex", "exec", "-"] and kwargs["input"] == "the prompt" and kwargs["stdin"] is None


def test_a_prompt_with_a_nul_byte_fails_without_running_instead_of_crashing(monkeypatch):
    run = Recorder()
    monkeypatch.setattr(digest.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="NUL"):
        digest.run_model(["agy", "-p", digest.PROMPT_ARG], "before\x00after", "/repo")
    assert run.calls == []


def test_a_prompt_too_long_for_the_command_line_fails_without_running(monkeypatch):
    run = Recorder()
    monkeypatch.setattr(digest.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="too long"):
        digest.run_model(["agy", "-p", digest.PROMPT_ARG], "é" * (digest.MAX_PROMPT_ARG_BYTES // 2 + 1), "/repo")
    assert run.calls == []


def test_antigravity_failing_hands_the_report_to_codex(monkeypatch):
    calls = []

    def model(argv, prompt, cwd):
        calls.append(argv[0])
        if argv[0] == "agy":
            raise RuntimeError("agy exited with 3: AGY_ERROR")
        return "ok"

    monkeypatch.setattr(digest, "run_model", model)
    argv, answer, errors = digest.ask(digest.clients(parse("--client", "antigravity")), "p", "/repo")
    assert (argv[0], answer, calls) == ("codex", "ok", ["agy", "codex"])
    assert errors == ["agy exited with 3: AGY_ERROR"]


def test_digest_help_lists_the_clients(capsys):
    with pytest.raises(SystemExit):
        main(["digest", "--help"])
    out = capsys.readouterr().out
    assert "antigravity" in out and "codex" in out


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("claude-code", "local Claude"),
        ("local-claude", "local Claude"),
        ("local-codex", "local Codex"),
        ("local-antigravity", "local Antigravity"),
        ("antigravity", "Antigravity subagents"),
        ("local-custom", "local custom client"),
        ("api-fallback", "API fallback"),
        ("something-new", "something-new"),
    ],
)
def test_the_weekly_page_names_each_summary_path(path, name):
    assert weekly.path_name(path) == name
