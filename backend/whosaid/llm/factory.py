from __future__ import annotations

from pathlib import Path

from whosaid.cache import ContentCache
from whosaid.config import Settings
from whosaid.errors import ConfigError
from whosaid.llm.cached import CachedLLM
from whosaid.llm.openai_compat import OpenAICompatClient

SARVAM_BASE_URL = "https://api.sarvam.ai/v1"


def build_llm(settings: Settings, *, fixture_dir: Path | None = None) -> CachedLLM:
    """The configured provider, wrapped in the cache. Provider, URL and model come from env."""
    provider = settings.llm_provider.lower()
    if provider not in {"ollama", "sarvam"}:
        raise ConfigError(f"LLM_PROVIDER must be 'ollama' or 'sarvam', got {settings.llm_provider!r}")
    if provider == "sarvam" and not settings.llm_api_key:
        raise ConfigError("LLM_PROVIDER=sarvam needs LLM_API_KEY (put it in backend/.env)")
    base_url = settings.llm_base_url
    if provider == "sarvam" and "localhost" in base_url:
        base_url = SARVAM_BASE_URL  # the default URL is Ollama's; don't send a Sarvam key there
    inner = OpenAICompatClient(
        provider=provider,
        base_url=base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        reasoning_effort=settings.llm_reasoning_effort,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    # The committed demo fixture is a read-only fallback: the demo replays identically anywhere.
    cache = ContentCache(settings.cache_dir, read_only_fallbacks=(fixture_dir,) if fixture_dir else ())
    return CachedLLM(inner, cache, provider=provider, reasoning_effort=settings.llm_reasoning_effort)
