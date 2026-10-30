from summaries.mode import API, CLAUDE_CODE, resolve_mode


def test_unset_mode_defaults_to_claude_code_without_warning():
    decision = resolve_mode("", provider_problem="no key")
    assert decision.mode == CLAUDE_CODE
    assert decision.warning is None


def test_api_mode_is_used_when_the_provider_is_ready():
    assert resolve_mode("api", provider_problem=None).mode == API


def test_api_mode_with_an_unready_provider_falls_back_and_says_why():
    """Flipping the variable before adding the secret must not stop the crawl."""
    decision = resolve_mode("api", provider_problem="the ANTHROPIC_API_KEY secret is not set")
    assert decision.mode == CLAUDE_CODE
    assert "ANTHROPIC_API_KEY" in decision.warning


def test_mode_value_is_normalised():
    assert resolve_mode("  API ", provider_problem=None).mode == API
    assert resolve_mode("Claude-Code", provider_problem=None).mode == CLAUDE_CODE


def test_unknown_mode_falls_back_to_claude_code_with_warning():
    decision = resolve_mode("openai", provider_problem=None)
    assert decision.mode == CLAUDE_CODE
    assert "openai" in decision.warning
