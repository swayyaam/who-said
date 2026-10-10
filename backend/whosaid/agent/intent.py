"""The task intent sent to AgntID's intent check, built ONLY from trusted data.

Never includes the message text: that is untrusted, and the intent is the user's side of the
comparison ("what was the agent asked to do?"). It is derived from the sender's trust level and the
router's category and decision, all computed in code.
"""

from __future__ import annotations

from whosaid.schemas import RoutingDecision, SenderTrust, TrustLevel

_SCOPE = {
    TrustLevel.UNKNOWN: "Only mute, digest, or block.",
    TrustLevel.KNOWN_CONTACT: "May reply and add calendar events.",
    TrustLevel.GROUP_ADMIN: "May reply, add calendar events, or pay the sender's registered payee.",
    TrustLevel.VERIFIED_BUSINESS: "May reply, add calendar events, or pay the sender's registered payee.",
}
_WHO = {
    TrustLevel.UNKNOWN: "an unknown sender",
    TrustLevel.KNOWN_CONTACT: "a known contact",
    TrustLevel.GROUP_ADMIN: "a group admin",
    TrustLevel.VERIFIED_BUSINESS: "a verified business",
}


def build_task_intent(trust: SenderTrust, routing: RoutingDecision | None = None) -> str:
    text = f"Triage a message from {_WHO[trust.level]}. {_SCOPE[trust.level]}"
    if routing is not None:
        text += f" Category: {routing.message_type.value}. Routing: {routing.action.value}."
    return text
