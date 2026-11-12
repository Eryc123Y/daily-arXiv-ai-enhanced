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


# Haiku wrote a whole chunk like this on 2026-11-11 (.cache/summaries/2026-11-11/merged/1794443731-chunk-000.out.txt):
# every block's five fields on one line. All 40 summaries were dropped.
INLINE = """=== 2601.04256
tldr: Uses descriptive set theory to determine the complexity of the family of monitorable sets in a countable topological space. motivation: Monitorability has been studied topologically, but the complexity of the family of monitorable sets had not been characterized. method: Analyzes monitorable sets in a countable space X, separately for second countable and non-second-countable X. result: For second countable X the family of monitorable sets is Π^0_3, and the exact complexities it can have are determined; for non-second-countable X it can be Π^1_1-complete. conclusion: The topology of the space, in particular second countability, decisively governs how complex the family of monitorable sets can be.
=== doi:10.46298/lmcs-22(4:15)2026
tldr: Gives a grounded inductive definition of α-equivalence for the untyped λ-calculus and shows that it conforms to the standard specification. motivation: α-equivalence is usually not defined inductively, which makes it hard to teach the untyped λ-calculus to undergraduates. method: Provides an inductive definition of α-equivalence and checks it against the specification in the literature. result: The definition conforms to the literature's specification, and the whole work is formalized in the Rocq Prover. conclusion: α-equivalence can be defined inductively, giving a simpler formal basis that is machine-checked in Rocq.
=== 2411.03006
tldr: Links the representational power of neural networks with piecewise linear activations to the extension complexity of polytopes, giving lower bounds on network size. motivation: Lower bounds on the size of ReLU and maxout networks are scarce, and tools from polyhedral geometry have not been applied to them. method: Shows that extension complexity lower-bounds any monotone or input-convex network that solves a linear optimization problem over a polytope, and introduces virtual extension complexity, which covers general networks as a difference of two linear programs. result: Yields exponential lower bounds for such networks on several problems, including maximum weight matching; proves that virtual extension complexity lower-bounds general networks, but derives no useful bounds on it; shows that a polytope can be optimized efficiently given a virtual extended formulation of small encoding size. conclusion: Virtual extension complexity deserves study in its own right, while useful lower bounds for general neural networks remain open.
"""


def test_parse_blocks_splits_fields_written_on_one_line():
    summaries, problems = parse_blocks(INLINE)
    assert problems == []
    assert list(summaries) == ["2601.04256", "doi:10.46298/lmcs-22(4:15)2026", "2411.03006"]
    first = summaries["2601.04256"]
    assert first["tldr"].startswith("Uses descriptive set theory") and first["tldr"].endswith("topological space.")
    assert first["motivation"] == "Monitorability has been studied topologically, but the complexity of the family of monitorable sets had not been characterized."
    assert first["method"] == "Analyzes monitorable sets in a countable space X, separately for second countable and non-second-countable X."
    assert first["result"].startswith("For second countable X") and first["result"].endswith("Π^1_1-complete.")
    assert first["conclusion"].startswith("The topology of the space")


def test_parse_blocks_splits_inline_fields_with_decorated_labels_and_fullwidth_colons():
    text = "=== 2610.00005\n**TLDR**：一 Motivation: 二 method: 三 **result**: 四 conclusion：五\n"
    summaries, problems = parse_blocks(text)
    assert problems == []
    assert summaries["2610.00005"] == {"tldr": "一", "motivation": "二", "method": "三", "result": "四", "conclusion": "五"}


def test_parse_blocks_still_rejects_an_inline_block_missing_a_field():
    text = "=== 2610.00006\ntldr: a motivation: b method: c conclusion: e\n"
    summaries, problems = parse_blocks(text)
    assert summaries == {}
    assert problems == ["2610.00006: incomplete block"]


def test_parse_blocks_still_rejects_an_inline_block_with_an_empty_field():
    text = "=== 2610.00007\ntldr: a motivation: method: c result: d conclusion: e\n"
    summaries, problems = parse_blocks(text)
    assert summaries == {}
    assert problems == ["2610.00007: incomplete block"]


def test_a_label_word_inside_a_well_formed_field_stays_text():
    """A block already complete line by line is not re-split, so 'result:' in a sentence is kept as written."""
    text = "=== 2610.00008\ntldr: a\nmotivation: b\nmethod: compare, then report the result: c\nresult: d\nconclusion: e\n"
    summaries, _ = parse_blocks(text)
    assert summaries["2610.00008"]["method"] == "compare, then report the result: c"
    assert summaries["2610.00008"]["result"] == "d"
