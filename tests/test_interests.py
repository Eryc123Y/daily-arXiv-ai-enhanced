from summaries.interests import keyword_matches, load_topics, topics_for


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
    assert names[0] == "2D-to-3D and stereo"
    assert len(names) == 4 and all(t["keywords"] for t in topics)
    assert "RLVR" in next(t for t in topics if t["name"] == "Weak supervision and data reuse")["keywords"]


def test_topics_read_title_abstract_and_tldr():
    topics = [{"name": "Stereo", "keywords": ["stereo"]}, {"name": "RL", "keywords": ["RLVR"]}]
    paper = {"title": "Depth", "summary": "A stereo method.", "AI": {"tldr": "Uses RLVR."}}
    assert topics_for(paper, topics) == ["Stereo", "RL"]
    assert topics_for({"title": "Stereotypes", "summary": ""}, topics) == []
