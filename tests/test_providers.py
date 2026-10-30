from summaries.providers import GEMINI_BASE_URL, resolve_provider


def test_default_is_anthropic_haiku_with_its_key():
    config, problem = resolve_provider({"ANTHROPIC_API_KEY": "x"})
    assert problem is None
    assert (config.provider, config.model, config.key_env, config.base_url) == ("anthropic", "claude-haiku-5-5", "ANTHROPIC_API_KEY", None)


def test_missing_key_is_reported_by_name():
    config, problem = resolve_provider({"SUMMARY_PROVIDER": "anthropic"})
    assert config is None and "ANTHROPIC_API_KEY" in problem


def test_openai_needs_a_model_and_its_key():
    _, problem = resolve_provider({"SUMMARY_PROVIDER": "openai", "OPENAI_API_KEY": "x"})
    assert "SUMMARY_MODEL" in problem
    config, problem = resolve_provider({"SUMMARY_PROVIDER": "OpenAI", "SUMMARY_MODEL": "m", "OPENAI_API_KEY": "x"})
    assert problem is None and (config.provider, config.model, config.base_url) == ("openai", "m", None)


def test_openai_compatible_servers_use_the_base_url():
    config, _ = resolve_provider(
        {"SUMMARY_PROVIDER": "openai", "SUMMARY_MODEL": "deepseek-chat", "OPENAI_API_KEY": "x", "OPENAI_BASE_URL": " https://api.deepseek.com/v1 "}
    )
    assert config.base_url == "https://api.deepseek.com/v1"


def test_gemini_uses_its_openai_compatible_endpoint_and_key():
    config, problem = resolve_provider({"SUMMARY_PROVIDER": "gemini", "SUMMARY_MODEL": "gemini-x", "GEMINI_API_KEY": "x"})
    assert problem is None
    assert (config.key_env, config.base_url) == ("GEMINI_API_KEY", GEMINI_BASE_URL)


def test_optional_settings_pass_through_and_unknown_providers_are_reported():
    config, _ = resolve_provider(
        {"SUMMARY_PROVIDER": "gemini", "SUMMARY_MODEL": "g", "GEMINI_API_KEY": "x", "SUMMARY_REASONING_EFFORT": "low", "SUMMARY_RESPONSE_FORMAT": "json_object"}
    )
    assert (config.reasoning_effort, config.response_format) == ("low", "json_object")
    config, problem = resolve_provider({"SUMMARY_PROVIDER": "mistral"})
    assert config is None and "mistral" in problem


def test_response_format_is_normalised_and_validated():
    base = {"SUMMARY_PROVIDER": "openai", "SUMMARY_MODEL": "m", "OPENAI_API_KEY": "x"}
    config, _ = resolve_provider({**base, "SUMMARY_RESPONSE_FORMAT": " JSON_Object "})
    assert config.response_format == "json_object"
    config, problem = resolve_provider({**base, "SUMMARY_RESPONSE_FORMAT": "xml"})
    assert config is None and "SUMMARY_RESPONSE_FORMAT" in problem


def test_the_anthropic_key_is_passed_stripped(monkeypatch):
    from summaries import anthropic_api, providers

    seen = {}
    monkeypatch.setattr(anthropic_api, "make_client", lambda api_key=None: seen.setdefault("key", api_key))
    env = {"ANTHROPIC_API_KEY": " sk-test \n"}
    config, _ = resolve_provider(env)
    providers.make_summarizer(config, env)
    assert seen["key"] == "sk-test"
