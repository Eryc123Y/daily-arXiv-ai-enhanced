from summaries.mode import CLAUDE_CODE, API, resolve_mode


def test_unset_mode_defaults_to_claude_code_without_warning():
    decision = resolve_mode("", api_key_present=False)
    assert decision.mode == CLAUDE_CODE
    assert decision.warning is None


def test_api_mode_is_used_only_when_the_key_is_present():
    assert resolve_mode("api", api_key_present=True).mode == API


def test_api_mode_without_key_falls_back_and_warns():
    """Flipping the variable before adding the secret must not stop the crawl."""
    decision = resolve_mode("api", api_key_present=False)
    assert decision.mode == CLAUDE_CODE
    assert "ANTHROPIC_API_KEY" in decision.warning


def test_mode_value_is_normalised():
    assert resolve_mode("  API ", api_key_present=True).mode == API
    assert resolve_mode("Claude-Code", api_key_present=True).mode == CLAUDE_CODE


def test_unknown_mode_falls_back_to_claude_code_with_warning():
    decision = resolve_mode("openai", api_key_present=True)
    assert decision.mode == CLAUDE_CODE
    assert "openai" in decision.warning
