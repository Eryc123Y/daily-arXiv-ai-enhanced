"""Which LLM API writes the summaries in API mode, from environment variables.

SUMMARY_PROVIDER   anthropic (default) | openai | gemini
SUMMARY_MODEL      model id; default claude-haiku-5-5 for anthropic, required otherwise
OPENAI_BASE_URL    for openai: any OpenAI-compatible server (DeepSeek, OpenRouter, ...)
SUMMARY_REASONING_EFFORT   optional, openai/gemini only (e.g. low)
SUMMARY_RESPONSE_FORMAT    json_schema (default) | json_object, openai/gemini only
Keys: ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY (repository secrets).
"""

from dataclasses import dataclass

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
ANTHROPIC_MODEL = "claude-haiku-5-5"
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    key_env: str
    base_url: str | None = None
    reasoning_effort: str | None = None
    response_format: str = "json_schema"


def _get(env, name):
    return (env.get(name) or "").strip()


def resolve_provider(env):
    """Return (config, None) when ready, or (None, what is missing)."""
    provider = _get(env, "SUMMARY_PROVIDER").lower() or "anthropic"
    if provider not in KEY_ENV:
        return None, f"unknown SUMMARY_PROVIDER '{provider}' (use anthropic, openai or gemini)"
    model = _get(env, "SUMMARY_MODEL") or (ANTHROPIC_MODEL if provider == "anthropic" else "")
    if not model:
        return None, f"SUMMARY_MODEL is not set; it is required for {provider}"
    key_env = KEY_ENV[provider]
    if not _get(env, key_env):
        return None, f"the {key_env} secret is not set"
    response_format = _get(env, "SUMMARY_RESPONSE_FORMAT").lower() or "json_schema"
    if response_format not in ("json_schema", "json_object"):
        return None, f"SUMMARY_RESPONSE_FORMAT '{response_format}' must be json_schema or json_object"
    base_url = {"gemini": GEMINI_BASE_URL, "openai": _get(env, "OPENAI_BASE_URL") or None}.get(provider)
    return (
        ProviderConfig(
            provider=provider,
            model=model,
            key_env=key_env,
            base_url=base_url,
            reasoning_effort=_get(env, "SUMMARY_REASONING_EFFORT") or None,
            response_format=response_format,
        ),
        None,
    )


def make_summarizer(config, env):
    """The `call(paper, language)` adapter for a resolved provider."""
    if config.provider == "anthropic":
        from summaries import anthropic_api

        return anthropic_api.make_call(anthropic_api.make_client(_get(env, config.key_env)), model=config.model)
    from summaries import openai_compat

    client = openai_compat.make_client(_get(env, config.key_env), config.base_url)
    return openai_compat.make_call(client, config.model, config.response_format, config.reasoning_effort)
