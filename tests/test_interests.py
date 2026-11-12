import json
import shutil
import subprocess
from pathlib import Path

import pytest

from summaries.interests import PRESETS, keyword_matches, load_topics, topics_for


def test_keywords_match_like_the_reading_page():
    """The same cases as tests/js/paper-data.test.js."""
    assert keyword_matches("Monocular 2D-to-3D video conversion", "2D to 3D")
    assert keyword_matches("Learning from Partial-Label data", "partial label")
    assert keyword_matches("Stereo matching with transformers", "stereo")
    assert keyword_matches("Novel views from a single image", "novel view")
    assert keyword_matches("We support PPOs and GRPO", "PPO")
    assert not keyword_matches("Gender stereotypes in LLMs", "stereo")
    assert not keyword_matches("We support robust training", "PPO")
    assert not keyword_matches("", "stereo")
    assert keyword_matches("一种立体视频生成方法", "立体")


def test_the_shipped_presets_load_with_their_keywords():
    topics = load_topics()
    names = [t["name"] for t in topics]
    assert names == [
        "2D-to-3D and stereo",
        "Weak supervision and data reuse",
        "Continual learning",
        "Data and representation",
        "Formal languages and reasoning",
        "Reinforcement learning and agents",
        "Language, cognition and learnability",
        "Learning theory and information",
    ]
    assert all(t["keywords"] for t in topics)
    keywords = {t["name"]: t["keywords"] for t in topics}
    assert "RLVR" in keywords["Weak supervision and data reuse"]
    assert {"Lean", "autoformalization", "Chomsky hierarchy"} <= set(keywords["Formal languages and reasoning"])
    assert {"RLHF", "Markov decision process", "credit assignment"} <= set(keywords["Reinforcement learning and agents"])
    # Too broad on its own (Eric, 2026-11-13): about 32 matches a day; the narrower keywords stay.
    assert "reinforcement learning" not in keywords["Reinforcement learning and agents"]
    assert {"BabyLM", "poverty of the stimulus", "iterated learning"} <= set(keywords["Language, cognition and learnability"])
    assert {"rate-distortion", "minimum description length", "PAC learning"} <= set(keywords["Learning theory and information"])


def test_a_capitalised_one_word_keyword_is_a_name_and_keeps_its_case():
    """"Lean" the proof assistant, not "lean" the adjective; phrases and acronyms match in any case."""
    assert keyword_matches("Formal proofs in Lean 4", "Lean")
    assert not keyword_matches("A lean, fast tokenizer", "Lean")
    assert keyword_matches("Training with rlhf", "RLHF")
    assert keyword_matches("Markov Decision Processes", "Markov decision process")
    topics = [{"name": "Formal", "keywords": ["Lean"]}]
    assert topics_for({"title": "Lean models for edge devices", "summary": "We keep the network lean."}, topics) == ["Formal"]
    assert topics_for({"title": "Small models for edge devices", "summary": "We keep the network lean."}, topics) == []


def test_topics_read_title_abstract_and_tldr():
    topics = [{"name": "Stereo", "keywords": ["stereo"]}, {"name": "RL", "keywords": ["RLVR"]}]
    paper = {"title": "Depth", "summary": "A stereo method.", "AI": {"tldr": "Uses RLVR."}}
    assert topics_for(paper, topics) == ["Stereo", "RL"]
    assert topics_for({"title": "Stereotypes", "summary": ""}, topics) == []


CASES = json.loads((Path(__file__).parent / "fixtures" / "keyword-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['keyword']}|{c['text']}")
def test_keyword_cases_shared_with_the_page(case):
    """tests/js/paper-data.test.js runs the same table against js/paper-data.js."""
    assert keyword_matches(case["text"], case["keyword"]) is case["matches"]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_python_parser_reads_every_topic_the_page_defines():
    script = "const {INTEREST_PRESETS} = require('./js/interest-presets.js'); console.log(JSON.stringify(INTEREST_PRESETS.topics))"
    page = json.loads(subprocess.run(["node", "-e", script], cwd=PRESETS.parent.parent, capture_output=True, text=True, check=True).stdout)
    assert [(t["name"], t["keywords"]) for t in load_topics()] == [(t["name"], t["keywords"]) for t in page]
