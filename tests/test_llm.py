import pytest

from summaries.llm import Retryable, Skip, summarize_all, summarize_paper

AI = {"tldr": "t", "motivation": "m", "method": "x", "result": "r", "conclusion": "c"}
PAPER = {"id": "2610.00001", "title": "T", "summary": "S"}


def calls(*effects):
    queue = list(effects)

    def call(paper, language):
        effect = queue.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect

    return call


def test_success_returns_the_cleaned_fields():
    outcome = summarize_paper(calls({k: f" {v} " for k, v in AI.items()}), PAPER, "English", sleep=lambda s: None)
    assert outcome.ai == AI and outcome.error is None and outcome.attempts == 1


def test_retryable_errors_back_off_and_honour_retry_after():
    sleeps = []
    call = calls(Retryable("429"), Retryable("429", retry_after=7), Retryable("500"), AI)
    outcome = summarize_paper(call, PAPER, "English", sleep=sleeps.append, base_delay=1.0)
    assert outcome.ai == AI
    assert sleeps == [1.0, 7.0, 4.0]


def test_retry_after_and_backoff_are_capped():
    sleeps = []
    summarize_paper(calls(Retryable("429", retry_after=900), AI), PAPER, "English", sleep=sleeps.append)
    assert sleeps == [60.0]


def test_skip_marks_the_paper_without_retry():
    outcome = summarize_paper(calls(Skip("refusal")), PAPER, "English", sleep=lambda s: None)
    assert outcome.ai is None and outcome.error == "refusal" and outcome.attempts == 1


def test_incomplete_fields_are_marked_without_retry():
    outcome = summarize_paper(calls({"tldr": "only"}), PAPER, "English", sleep=lambda s: None)
    assert outcome.ai is None and "incomplete" in outcome.error


def test_giving_up_after_the_last_attempt():
    outcome = summarize_paper(calls(*[Retryable("503")] * 3), PAPER, "English", max_attempts=3, sleep=lambda s: None)
    assert outcome.ai is None and "503" in outcome.error and outcome.attempts == 3


def test_other_exceptions_stop_the_run():
    with pytest.raises(PermissionError):
        summarize_paper(calls(PermissionError("bad key")), PAPER, "English", sleep=lambda s: None)


def test_summarize_all_keeps_order():
    papers = [{**PAPER, "id": str(i)} for i in range(4)]
    outcomes = summarize_all(lambda p, lang: AI, papers, "English", max_workers=2, sleep=lambda s: None)
    assert [o.paper_id for o in outcomes] == ["0", "1", "2", "3"]
