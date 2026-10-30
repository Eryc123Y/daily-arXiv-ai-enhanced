from summaries.records import (
    clean_ai,
    dedupe_by_id,
    dump_jsonl,
    merge_summaries,
    parse_jsonl,
    pending_papers,
)

FULL_AI = {
    "tldr": "一句话总结",
    "motivation": "动机",
    "method": "方法",
    "result": "结果",
    "conclusion": "结论",
}


def paper(paper_id, **extra):
    return {
        "id": paper_id,
        "categories": ["cs.CV"],
        "title": f"Title {paper_id}",
        "authors": ["A. Author"],
        "summary": f"Abstract of {paper_id}.",
        **extra,
    }


def test_clean_ai_strips_whitespace_and_drops_unknown_keys():
    cleaned = clean_ai({**{k: f"  {v} " for k, v in FULL_AI.items()}, "extra": "x"})
    assert cleaned == FULL_AI


def test_clean_ai_rejects_missing_empty_or_non_string_fields():
    assert clean_ai({**FULL_AI, "method": ""}) is None
    assert clean_ai({**FULL_AI, "result": None}) is None
    assert clean_ai({k: v for k, v in FULL_AI.items() if k != "tldr"}) is None
    assert clean_ai("not a dict") is None


def test_dedupe_keeps_first_occurrence_in_order():
    """The crawler emits a paper once per category page it appears on."""
    rows = [paper("1"), paper("2"), paper("1", title="dup"), paper("3")]
    assert [r["id"] for r in dedupe_by_id(rows)] == ["1", "2", "3"]
    assert dedupe_by_id(rows)[0]["title"] == "Title 1"


def test_parse_and_dump_jsonl_round_trip_skips_blank_lines():
    rows = [paper("1"), {"id": "2", "title": "中文"}]
    text = dump_jsonl(rows)
    assert "中文" in text  # written as UTF-8, not \u escapes
    assert parse_jsonl(text + "\n\n") == rows
    assert parse_jsonl("") == []


def test_pending_papers_are_raw_papers_without_a_complete_summary():
    raw = [paper("1"), paper("2"), paper("3")]
    ai_records = [{**paper("1"), "AI": FULL_AI}, {**paper("2"), "AI": {"tldr": "only"}}]
    assert [p["id"] for p in pending_papers(raw, ai_records)] == ["2", "3"]


def test_merge_keeps_raw_order_and_only_complete_records():
    raw = [paper("1"), paper("2"), paper("3")]
    existing = [{**paper("3"), "AI": FULL_AI, "code_url": "https://github.com/a/b"}]
    new = {"1": FULL_AI, "2": {**FULL_AI, "conclusion": "  "}}

    merged = merge_summaries(raw, existing, new)

    assert [r["id"] for r in merged] == ["1", "3"]
    assert merged[0]["AI"] == FULL_AI
    assert merged[0]["title"] == "Title 1"
    assert merged[1]["code_url"] == "https://github.com/a/b"


def test_merge_ignores_summaries_for_unknown_ids_and_does_not_mutate_inputs():
    raw = [paper("1")]
    new = {"1": FULL_AI, "999": FULL_AI}
    merged = merge_summaries(raw, [], new)
    assert [r["id"] for r in merged] == ["1"]
    assert "AI" not in raw[0]


def test_merge_does_not_overwrite_an_existing_summary():
    """Re-running a chunk must not replace a summary that is already published."""
    raw = [paper("1")]
    existing = [{**paper("1"), "AI": FULL_AI}]
    merged = merge_summaries(raw, existing, {"1": {**FULL_AI, "tldr": "新的"}})
    assert merged[0]["AI"]["tldr"] == "一句话总结"


def test_dedupe_skips_records_without_an_id():
    assert [r["id"] for r in dedupe_by_id([{}, {"id": ""}, paper("1"), "junk"])] == ["1"]
