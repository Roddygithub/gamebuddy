"""Build the configured provider."""

from __future__ import annotations

from gamebro.config import CHEAP_COACH_MODEL, Config
from gamebro.llm.base import LLMProvider


class ProviderError(RuntimeError):
    pass


def make_provider(cfg: Config, model: str | None = None) -> LLMProvider:
    llm = cfg.llm
    provider = llm.provider
    model = model or llm.model
    key = cfg.resolve_api_key()
    if provider == "codex":
        from gamebro.llm.codex_provider import CodexProvider

        chosen = "" if model.startswith("claude") else model  # ignore a leftover Anthropic default
        return CodexProvider(model=chosen, effort=llm.effort, binary=llm.codex_binary)
    if provider == "anthropic":
        if not key:
            raise ProviderError("missing_api_key")
        from gamebro.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=model, api_key=key, base_url=llm.base_url, effort=llm.effort)
    if provider == "openai":
        if not key:
            raise ProviderError("missing_api_key")
        from gamebro.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(model=model, api_key=key, base_url=llm.base_url, temperature=llm.temperature)
    if provider == "ollama":
        from gamebro.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            model=model,
            api_key=key or "ollama",
            base_url=llm.base_url or "http://localhost:11434/v1",
            temperature=llm.temperature,
            vision=llm.vision,
            name="ollama",
        )
    if provider == "openai_compatible":
        from gamebro.llm.openai_provider import OpenAIProvider

        if not llm.base_url:
            raise ProviderError("missing_base_url")
        return OpenAIProvider(
            model=model,
            api_key=key,
            base_url=llm.base_url,
            temperature=llm.temperature,
            vision=llm.vision,
            name="openai_compatible",
        )
    raise ProviderError(f"unknown_provider:{provider}")


def coach_model(cfg: Config) -> str:
    return cfg.coach.model or CHEAP_COACH_MODEL.get(cfg.llm.provider, "") or cfg.llm.model
