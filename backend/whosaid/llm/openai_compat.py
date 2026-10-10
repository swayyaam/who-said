"""One client for any OpenAI-compatible /chat/completions endpoint (Ollama, Sarvam, ...).

Adapted in spirit from the old Anthropic client: structured errors, no secret in any message.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from whosaid.errors import LLMError
from whosaid.llm.base import ChatResult, ProposedToolCall


def parse_chat_response(body: dict[str, Any]) -> ChatResult:
    """Turn a /chat/completions body into a ChatResult. Malformed tool calls are counted, not raised."""
    try:
        choice = body["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("the model response had no choices[0].message") from exc

    calls: list[ProposedToolCall] = []
    malformed = 0
    for i, raw in enumerate(message.get("tool_calls") or []):
        try:
            name = raw["function"]["name"]
            args = raw["function"].get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args) if args.strip() else {}
            if not isinstance(args, dict):
                raise ValueError("arguments are not an object")
            calls.append(ProposedToolCall(id=raw.get("id") or f"call_{i}", name=name, arguments=args))
        except (KeyError, TypeError, ValueError):
            malformed += 1

    usage = body.get("usage") or {}
    # Keep only OpenAI-standard fields on the message we replay; drop provider extras (e.g. reasoning).
    assistant = {"role": "assistant", "content": message.get("content") or ""}
    if message.get("tool_calls"):
        assistant["tool_calls"] = message["tool_calls"]
    return ChatResult(
        content=message.get("content") or "",
        tool_calls=calls,
        assistant_message=assistant,
        finish_reason=choice.get("finish_reason"),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        malformed_tool_calls=malformed,
    )


class OpenAICompatClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str = "",
        reasoning_effort: str = "none",
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(timeout=timeout_seconds, headers=headers, transport=transport)

    def request_body(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0, "stream": False}
        if tools:
            body["tools"] = tools
        if self.provider == "ollama" and self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort  # "none" turns thinking off
        return body

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatResult:
        started = time.perf_counter()
        try:
            response = await self._http.post(self._url, json=self.request_body(messages, tools))
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"{self.provider} returned HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"could not reach {self.provider} at {self._url}: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise LLMError(f"{self.provider} returned a non-JSON body") from exc
        result = parse_chat_response(body)
        result.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return result

    async def aclose(self) -> None:
        await self._http.aclose()
