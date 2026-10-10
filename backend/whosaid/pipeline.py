"""Run a whole dataset: per message, trust -> route -> (agent if actionable) -> result.

Concurrency is bounded by a semaphore. Progress is reported through an ``Emitter``; each
finished ``MessageResult`` is also passed to ``on_result``. Both enforcement modes run this
exact code; only the gateway differs, which is what makes OFF vs ON a fair comparison.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from whosaid.agent.loop import run_agent
from whosaid.agent.tool_gateway import ToolGateway
from whosaid.config import Settings
from whosaid.events import Emitter, noop_emit
from whosaid.ingest.dataset import Dataset
from whosaid.llm.base import LLMClient
from whosaid.logging_setup import log_event
from whosaid.router import route
from whosaid.schemas import AgentTrace, EventType, Message, MessageResult
from whosaid.scoring import controls_ok, executed_tools, harmful_money_lost, harmful_tools_executed, mark_harm, money_moved
from whosaid.trust import TrustProvider, get_trust_provider

GatewayFactory = Callable[[], ToolGateway]


async def process_message(
    message: Message,
    *,
    dataset: Dataset,
    trust_provider: TrustProvider,
    llm: LLMClient,
    gateway_factory: GatewayFactory,
    settings: Settings,
    emit: Emitter = noop_emit,
) -> MessageResult:
    emit(EventType.MESSAGE_STARTED, message.message_id, {"user_id": message.user_id})
    trust = trust_provider.assess(message)
    routing = route(message, trust, dataset)
    emit(EventType.MESSAGE_ROUTED, message.message_id, {
        "action": routing.action.value, "message_type": routing.message_type.value, "rule": routing.rule,
        "actionable": routing.actionable, "sender_trust": trust.level.value,
    })
    log_event("message.routed", message_id=message.message_id, action=routing.action.value, rule=routing.rule,
              actionable=routing.actionable, sender_trust=trust.level.value)

    label = dataset.labels.get(message.message_id)
    trace = AgentTrace()
    if routing.actionable:
        media = dataset.media.get(message.media_id) if message.media_id else None
        async with gateway_factory() as gateway:
            trace = await run_agent(
                llm=llm, gateway=gateway, message=message, trust=trust, nonce_secret=settings.nonce_secret,
                media_description=media.description if media else None, max_turns=settings.agent_max_turns, emit=emit,
            )
        trace.attempts = mark_harm(trace.attempts, label)

    result = MessageResult(
        message_id=message.message_id,
        user_id=message.user_id,
        text=message.message_text,
        sender=trust.sender,
        trust=trust,
        routing=routing,
        scenario=label,
        agent=trace,
        executed_tools=executed_tools(trace.attempts),
        money_moved_inr=money_moved(trace.attempts),
        harmful_executed=harmful_tools_executed(trace.attempts),
        harmful_money_lost_inr=harmful_money_lost(trace.attempts),
        legit_actions_ok=controls_ok(trace, label),
    )
    emit(EventType.MESSAGE_COMPLETED, message.message_id, result.model_dump(mode="json"))
    return result


async def run_dataset(
    dataset: Dataset,
    *,
    llm: LLMClient,
    gateway_factory: GatewayFactory,
    settings: Settings,
    emit: Emitter = noop_emit,
    on_result: Callable[[MessageResult], None] | None = None,
    only: set[str] | None = None,
    limit: int | None = None,
    concurrency: int | None = None,
) -> list[MessageResult]:
    """Process the dataset's messages (optionally filtered). Results come back in dataset order."""
    messages = [m for m in dataset.messages if only is None or m.message_id in only]
    if limit is not None:
        messages = messages[:limit]
    trust_provider = get_trust_provider(messages[0].channel, dataset) if messages else None
    semaphore = asyncio.Semaphore(max(1, concurrency or settings.agent_concurrency))

    async def one(message: Message) -> MessageResult:
        async with semaphore:
            result = await process_message(
                message, dataset=dataset, trust_provider=trust_provider, llm=llm,  # type: ignore[arg-type]
                gateway_factory=gateway_factory, settings=settings, emit=emit,
            )
        if on_result:
            on_result(result)
        return result

    return list(await asyncio.gather(*(one(m) for m in messages)))
