from summaries.blocks import format_chunk, parse_blocks

GOOD = """=== 2610.00001
tldr: 提出一种立体视频生成方法。
motivation: 现有方法缺少视差一致性。
method: 使用深度引导的扩散模型。
result: 在两个数据集上优于基线。
conclusion: 方法简单有效。

=== 2610.00002
TLDR：第二篇论文。
Motivation：动机二。
method: 方法二，
  跨行继续。
result: 结果二。
conclusion: 结论二。
"""


def test_format_chunk_lists_id_title_and_abstract_on_single_lines():
    text = format_chunk(
        [{"id": "2610.00001", "title": "A\nTitle", "summary": "Line one.\nLine two."}]
    )
    assert "=== 2610.00001" in text
    assert "title: A Title" in text
    assert "abstract: Line one. Line two." in text


def test_parse_blocks_reads_every_complete_block():
    summaries, problems = parse_blocks(GOOD)
    assert problems == []
    assert set(summaries) == {"2610.00001", "2610.00002"}
    assert summaries["2610.00001"]["method"] == "使用深度引导的扩散模型。"


def test_parse_blocks_accepts_fullwidth_colons_case_and_continuation_lines():
    summaries, _ = parse_blocks(GOOD)
    second = summaries["2610.00002"]
    assert second["tldr"] == "第二篇论文。"
    assert second["motivation"] == "动机二。"
    assert second["method"] == "方法二， 跨行继续。"


def test_parse_blocks_reports_incomplete_blocks_instead_of_returning_them():
    text = "=== 2610.00003\ntldr: 只有一个字段\n"
    summaries, problems = parse_blocks(text)
    assert summaries == {}
    assert problems and "2610.00003" in problems[0]


def test_parse_blocks_ignores_text_before_the_first_block_and_keeps_first_duplicate():
    text = "Here are the summaries:\n" + GOOD + GOOD.replace("方法简单有效", "重复")
    summaries, problems = parse_blocks(text)
    assert summaries["2610.00001"]["conclusion"] == "方法简单有效。"
    assert any("duplicate" in p for p in problems)


def test_parse_blocks_strips_markdown_decoration_from_labels():
    text = "=== 2610.00004\n**tldr**: a\n- motivation: b\nmethod: c\nresult: d\nconclusion: e\n"
    summaries, problems = parse_blocks(text)
    assert problems == []
    assert summaries["2610.00004"] == {
        "tldr": "a",
        "motivation": "b",
        "method": "c",
        "result": "d",
        "conclusion": "e",
    }
