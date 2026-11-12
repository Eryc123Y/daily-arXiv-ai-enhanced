"""ensure-day fills missing feed abstracts through ABSTRACTS_COMMAND (tests/fixtures/fake_abstracts.py)."""

import json
import sys
from pathlib import Path

import pytest
from test_cli import branch_file, data_repo, paper, pipeline, run  # noqa: F401 (fixtures)

from conftest import git, seed_data_branch
from summaries import abstract_retry, abstracts
from summaries.records import dump_jsonl, parse_jsonl

FAKE = Path(__file__).parent / "fixtures" / "fake_abstracts.py"
TODAY = "2026-11-09"


def journal(n, has_abstract=False, **extra):
    """A feed record as the feed publishes it, without its abstract."""
    return {
        "id": f"doi:10.1109/tip.2026.{n}",
        "source": "crossref",
        "title": f"Journal paper {n}",
        "authors": ["Ada Lovelace"],
        "venue": "IEEE TIP",
        "published": "2026-11-01",
        "doi": f"10.1109/tip.2026.{n}",
        "oa_url": None,
        "url": f"https://doi.org/10.1109/tip.2026.{n}",
        "categories": [],
        "has_abstract": has_abstract,
        **extra,
    }


@pytest.fixture
def setup(pipeline, tmp_path, monkeypatch):  # noqa: F811 (pytest fixture argument)
    """ensure-day on TODAY with the fake command; setup.found({id: (abstract, source)}) sets what it finds."""
    known = tmp_path / "known.json"
    log = tmp_path / "asked.jsonl"
    monkeypatch.setenv("ABSTRACTS_COMMAND", json.dumps([sys.executable, str(FAKE)]))
    monkeypatch.setenv("FAKE_ABSTRACTS", str(known))
    monkeypatch.setenv("FAKE_ABSTRACTS_LOG", str(log))
    for name in ("FAKE_ABSTRACTS_FAIL", "FAKE_ABSTRACTS_GARBLE"):
        monkeypatch.delenv(name, raising=False)
    known.write_text("{}")
    pipeline.found = lambda found: known.write_text(json.dumps(found))
    pipeline.asked = lambda: parse_jsonl(log.read_text()) if log.exists() else []
    pipeline.work = pipeline.clone / ".cache" / "summaries"

    def ensure(capsys):
        code, out = pipeline.run(capsys=capsys)
        return code, json.loads(out)["abstracts"]

    pipeline.ensure = ensure
    return pipeline


def seed(setup, days):
    seed_data_branch(setup.clone.parent, setup.remote, {f"data/{d}.jsonl": dump_jsonl(rows) for d, rows in days.items()})


def flags(setup, day):
    return {r["id"]: r.get("has_abstract") for r in parse_jsonl(branch_file(setup.remote, f"data/{day}.jsonl"))}


# --- Off ------------------------------------------------------------------------------


def test_without_the_command_the_step_is_off(pipeline, capsys):  # noqa: F811 (pytest fixture argument)
    pipeline.seed({"2026-11-06": [paper("A"), journal(1)]})

    _, out = pipeline.run(capsys=capsys)

    assert json.loads(out)["abstracts"] == {"status": "off"}


def test_a_command_that_is_not_a_json_list_is_an_error(setup, monkeypatch, capsys):
    seed(setup, {"2026-11-06": [journal(1)]})
    monkeypatch.setenv("ABSTRACTS_COMMAND", "litscout abstracts")

    code, report = setup.ensure(capsys)

    assert code == 0 and report["status"] == "error" and "ABSTRACTS_COMMAND" in report["reason"]
    assert setup.asked() == []


# --- Selection ------------------------------------------------------------------------


def test_only_feed_records_lacking_an_abstract_in_the_last_60_days_are_asked_newest_first(setup, capsys):
    seed(setup, {
        "2026-09-09": [journal(1)],  # 61 days before today: outside the window
        "2026-09-10": [journal(2)],  # 60 days: inside
        "2026-11-02": [paper("A"), journal(3, has_abstract=True), journal(4), {**journal(5), "has_abstract": None}],
        "2026-11-06": [journal(6), journal(7, id="2411.03006", doi=None, source="openalex")],
    })
    abstracts.save(setup.work, {"doi:10.1109/tip.2026.6": "Already here."})

    code, report = setup.ensure(capsys)

    assert code == 0
    assert setup.asked() == [
        {"id": "2411.03006", "arxiv": "2411.03006", "title": "Journal paper 7"},
        {"id": "doi:10.1109/tip.2026.4", "doi": "10.1109/tip.2026.4", "title": "Journal paper 4"},
        {"id": "doi:10.1109/tip.2026.2", "doi": "10.1109/tip.2026.2", "title": "Journal paper 2"},
    ]
    assert report == {"status": "ok", "asked": 3, "filled": 0, "by_source": {}, "still_lacking": 3, "commit": ""}


def test_at_most_200_records_are_asked_newest_day_first(setup, capsys):
    seed(setup, {
        "2026-11-05": [journal(n) for n in range(150)],
        "2026-11-06": [journal(n) for n in range(150, 210)],
    })

    _, report = setup.ensure(capsys)

    asked = [line["id"] for line in setup.asked()]
    assert len(asked) == 200
    assert asked[:60] == [f"doi:10.1109/tip.2026.{n}" for n in range(150, 210)]
    assert (report["asked"], report["still_lacking"]) == (200, 210)


def test_nothing_lacking_means_the_command_is_not_run(setup, capsys):
    seed(setup, {"2026-11-06": [paper("A"), journal(1, has_abstract=True)]})

    _, report = setup.ensure(capsys)

    assert report == {"status": "ok", "asked": 0, "filled": 0, "by_source": {}, "still_lacking": 0, "commit": ""}
    assert setup.asked() == []


# --- Filling ----------------------------------------------------------------------------


def test_found_abstracts_are_saved_locally_and_flagged_on_their_own_days(setup, capsys):
    seed(setup, {
        "2026-10-20": [journal(1), journal(2)],
        "2026-11-06": [paper("A"), journal(3), journal(4)],
    })
    setup.found({
        "doi:10.1109/tip.2026.1": ["Abstract one.", "openalex"],
        "doi:10.1109/tip.2026.3": ["Abstract three.", "crossref"],
        "doi:10.1109/tip.2026.4": ["", "crossref"],  # an empty abstract is no abstract
    })
    unrelated = git(setup.remote, "rev-parse", "data")

    code, report = setup.ensure(capsys)

    assert code == 0
    assert {k: report[k] for k in ("status", "asked", "filled", "by_source", "still_lacking")} == {
        "status": "ok", "asked": 4, "filled": 2, "by_source": {"crossref": 1, "openalex": 1}, "still_lacking": 2,
    }
    assert report["commit"] and report["commit"] != unrelated
    assert abstracts.load(setup.work) == {"doi:10.1109/tip.2026.1": "Abstract one.", "doi:10.1109/tip.2026.3": "Abstract three."}
    assert flags(setup, "2026-10-20") == {"doi:10.1109/tip.2026.1": True, "doi:10.1109/tip.2026.2": False}
    assert flags(setup, "2026-11-06") == {"A": None, "doi:10.1109/tip.2026.3": True, "doi:10.1109/tip.2026.4": False}
    # The abstract text stays local: the public branch only carries the flag.
    assert "Abstract one." not in branch_file(setup.remote, "data/2026-10-20.jsonl")


def test_filled_papers_become_pending_for_the_summary_step(setup, capsys):
    seed(setup, {"2026-11-06": [journal(1), journal(2)]})
    setup.found({"doi:10.1109/tip.2026.1": ["Abstract one.", "openalex"]})

    setup.ensure(capsys)

    _, out = run(setup.clone, "status", "--days", "36500", capsys=capsys)
    day = next(d for d in json.loads(out)["dates"] if d["date"] == "2026-11-06")
    assert (day["pending"], day["no_abstract"]) == (1, 1)


def test_a_second_run_does_not_ask_for_what_the_first_one_filled(setup, capsys):
    seed(setup, {"2026-11-06": [journal(1), journal(2)]})
    setup.found({"doi:10.1109/tip.2026.1": ["Abstract one.", "openalex"]})
    setup.ensure(capsys)

    _, report = setup.ensure(capsys)

    assert report["asked"] == 1 and setup.asked()[-1]["id"] == "doi:10.1109/tip.2026.2"


# --- Errors -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("variable", "value", "reason"),
    [
        ("FAKE_ABSTRACTS_FAIL", "rate limited by OpenAlex", "rate limited by OpenAlex"),
        ("FAKE_ABSTRACTS_GARBLE", "not json", "line 2"),
        ("FAKE_ABSTRACTS_GARBLE", '{"id": "doi:10.1109/tip.2026.9", "abstract": null, "source": null}', "line 2"),
        ("FAKE_ABSTRACTS_GARBLE", '{"id": "doi:10.1109/tip.2026.2", "abstract": 7, "source": null}', "line 2"),
    ],
)
def test_a_failing_or_malformed_answer_saves_and_flags_nothing(setup, monkeypatch, capsys, variable, value, reason):
    seed(setup, {"2026-11-06": [journal(1), journal(2)]})
    setup.found({"doi:10.1109/tip.2026.1": ["Abstract one.", "openalex"], "doi:10.1109/tip.2026.2": ["Two.", "crossref"]})
    monkeypatch.setenv(variable, value)

    code, report = setup.ensure(capsys)

    assert code == 0 and report["status"] == "error" and reason in report["reason"]
    assert report["asked"] == 2 and report["filled"] == 0
    assert not abstracts.path(setup.work).exists()
    assert flags(setup, "2026-11-06") == {"doi:10.1109/tip.2026.1": False, "doi:10.1109/tip.2026.2": False}


def test_an_answer_with_too_few_lines_is_an_error():
    asked = [journal(1), journal(2)]
    reply = json.dumps({"id": "doi:10.1109/tip.2026.1", "abstract": "A.", "source": "openalex"}) + "\n"

    with pytest.raises(abstract_retry.AbstractsError, match="1 lines for 2 papers"):
        abstract_retry.parse_reply(reply, [r["id"] for r in asked])


class _RefusingBranch:
    """A data branch whose push always fails."""

    def __init__(self, files):
        self.files = files

    def fetch(self):
        pass

    def list_files(self, prefix):
        return [p for p in self.files if p.startswith(prefix)]

    def read(self, path):
        return self.files.get(path)

    def publish(self, files, message):
        from summaries.databranch import PublishError

        raise PublishError("Could not push to data after 4 attempts: rejected")


def test_a_failed_push_of_the_flags_is_reported_and_the_abstracts_stay_saved(tmp_path, monkeypatch):
    branch = _RefusingBranch({"data/2026-11-06.jsonl": dump_jsonl([journal(1)])})
    known = tmp_path / "known.json"
    known.write_text(json.dumps({"doi:10.1109/tip.2026.1": ["Abstract one.", "openalex"]}))
    monkeypatch.setenv("FAKE_ABSTRACTS", str(known))
    monkeypatch.delenv("FAKE_ABSTRACTS_LOG", raising=False)
    env = {"ABSTRACTS_COMMAND": json.dumps([sys.executable, str(FAKE)])}

    report = abstract_retry.run(branch, TODAY, tmp_path, tmp_path / "work", env)

    assert report["status"] == "error" and "rejected" in report["reason"] and report["filled"] == 1
    # The paper is pending for run-local all the same: pending follows the local abstract, not the flag.
    assert abstracts.load(tmp_path / "work") == {"doi:10.1109/tip.2026.1": "Abstract one."}
