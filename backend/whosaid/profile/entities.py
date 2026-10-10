"""Which entities a message touches: who sent it, which group, which business, what kind."""

from __future__ import annotations

from enum import StrEnum

from whosaid.cues import extract_cues
from whosaid.schemas import ConversationType, Message


class EntityKind(StrEnum):
    SENDER = "sender"
    BUSINESS = "business"
    GROUP = "group"
    CATEGORY = "category"


# Most specific first: the first with enough evidence speaks for the message.
SPECIFICITY = (EntityKind.SENDER, EntityKind.BUSINESS, EntityKind.GROUP, EntityKind.CATEGORY)


def entity_key(kind: EntityKind, entity_id: str) -> str:
    return f"{kind.value}:{entity_id}"


def categorize(message: Message) -> str:
    """A coarse message category from lexical cues (promotion, payment, event, ...)."""
    cues = extract_cues(message.message_text, message.user_id)
    if cues.promotional and not cues.wants_payment:
        return "promotion"
    if message.forwarded_count >= 5:
        return "forward"
    if cues.wants_payment:
        return "payment"
    if cues.wants_schedule:
        return "event"
    if message.conversation_type is ConversationType.BUSINESS:
        return "business_update"
    if cues.urgent:
        return "urgent"
    return "personal"


def entities_of(message: Message) -> list[tuple[EntityKind, str]]:
    """The (kind, id) pairs a message touches, in specificity order."""
    found: list[tuple[EntityKind, str]] = []
    if message.conversation_type is ConversationType.BUSINESS:
        if message.business_id:
            found.append((EntityKind.BUSINESS, message.business_id))
    elif message.sender_user_id:
        found.append((EntityKind.SENDER, message.sender_user_id))
    if message.group_id:
        found.append((EntityKind.GROUP, message.group_id))
    found.append((EntityKind.CATEGORY, categorize(message)))
    return sorted(found, key=lambda kv: SPECIFICITY.index(kv[0]))
