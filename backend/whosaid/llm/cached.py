"""Wraps any LLM client so every call goes through the content-hash cache."""

from __future__ import annotations

from typing import Any

from whosaid.cache import ContentCache, content_key
from whosaid.llm.base import ChatResult, LLMClient
from whosaid.logging_setup import log_event

# Bump when a change to prompts or parsing should invalidate every cached answer.
LLM_CACHE_VERSION = "1"


class CachedLLM:
    def __init__(self, inner: LLMClient, cache: ContentCache, *, provider: str, reasoning_effort: str) -> None:
        self._inner = inner
        self._cache = cache
        self._provider = provider
        self._effort = reasoning_effort
        self.model = inner.model

    def cache_key(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
        return content_key({
            "v": LLM_CACHE_VERSION,
            "provider": self._provider,
            "model": self.model,
            "reasoning_effort": self._effort,
            "messages": messages,
            "tools": tools,
        })

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatResult:
        key = self.cache_key(messages, tools)
        hit = self._cache.get(key)
        if hit is not None:
            result = ChatResult.model_validate(hit)
            result.cached = True
            log_event("llm.call", cache="hit", key=key[:12], model=self.model)
            return result
        result = await self._inner.chat(messages, tools)
        # A reply with unparseable tool calls is not worth freezing: let the next run retry it.
        if result.malformed_tool_calls == 0:
            self._cache.put(key, result.model_dump(mode="json"))
        log_event("llm.call", cache="miss", key=key[:12], model=self.model, latency_ms=result.latency_ms,
                  tool_calls=len(result.tool_calls), prompt_tokens=result.prompt_tokens)
        return result

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close:
            await close()
