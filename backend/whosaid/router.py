"""notify / digest / mute triage, plus the "should the agent act on this?" flag.

Deterministic rules in precedence order (a simplified port of the old policy engine).
The first rule that fires decides. ``actionable`` is independent of the action: a scam
asking for an OTP is routed to mute *and* is actionable, because an agent with tools could
still be talked into acting on it. Messages with nothing to act on skip the LLM entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from whosaid.cues import extract_cues
from whosaid.ingest.dataset import Dataset
from whosaid.schemas import (
    Action,
    ConversationType,
    Cues,
    Message,
    MessageType,
    RoutingDecision,
    SenderTrust,
    TrustLevel,
)

FORWARDED_BROADCAST_THRESHOLD = 5


@dataclass(frozen=True)
class _Verdict:
    action: Action
    message_type: MessageType
    rule: str
    reason: str


_Rule = Callable[[Message, SenderTrust, Cues, Dataset], "_Verdict | None"]


def _credential_request(m, t, c, d):
    if c.wants_secret:
        return _Verdict(Action.MUTE, MessageType.SCAM, "CREDENTIAL_REQUEST", "Asks for a code or secret; no legitimate sender needs one.")


def _impersonation(m, t, c, d):
    if m.conversation_type is ConversationType.BUSINESS and not t.signals.get("verified") and (
        t.signals.get("domain_state") == "mismatch" or not t.signals.get("identity_consistent", True)
    ):
        return _Verdict(Action.MUTE, MessageType.SCAM, "IMPERSONATION", "Unverified business account presenting under a brand or domain it does not own.")


def _unknown_payment(m, t, c, d):
    if c.wants_payment and t.level is TrustLevel.UNKNOWN:
        return _Verdict(Action.MUTE, MessageType.SCAM, "UNKNOWN_SENDER_PAYMENT", "Payment demand from a sender with no established trust.")


def _group_muted(m, t, c, d):
    ms = d.membership(m.group_id, m.user_id)
    if ms is not None and ms.group_muted_by_user and not c.addresses_recipient:
        return _Verdict(Action.MUTE, MessageType.UNKNOWN, "GROUP_MUTED", "The user muted this group and the message does not address them directly.")


def _promotion(m, t, c, d):
    if c.promotional and not c.wants_payment:
        rel = d.relationship(m.user_id, m.business_id)
        opted_out = rel is not None and (not rel.allows_promotions or rel.promotions_opted_out_at is not None)
        if t.level is TrustLevel.UNKNOWN or opted_out:
            return _Verdict(Action.MUTE, MessageType.PROMOTION, "PROMOTION_UNWANTED", "Promotion the user has opted out of or from a sender they do not know.")
        return _Verdict(Action.DIGEST, MessageType.PROMOTION, "PROMOTION", "Promotion from a sender the user deals with; fine for the digest.")


def _broadcast(m, t, c, d):
    if m.forwarded_count >= FORWARDED_BROADCAST_THRESHOLD and not c.addresses_recipient:
        return _Verdict(Action.MUTE, MessageType.FORWARD, "FORWARDED_BROADCAST", "Heavily forwarded chain message.")


def _trusted_payment(m, t, c, d):
    if c.wants_payment and t.level in (TrustLevel.GROUP_ADMIN, TrustLevel.VERIFIED_BUSINESS):
        return _Verdict(Action.NOTIFY, MessageType.PAYMENT, "TRUSTED_PAYMENT", "Payment request from an admin or verified business the user deals with.")


def _schedule(m, t, c, d):
    if c.wants_schedule and t.level is not TrustLevel.UNKNOWN:
        return _Verdict(Action.NOTIFY, MessageType.EVENT, "SCHEDULE", "A plan or event from someone the user knows.")


def _direct_address(m, t, c, d):
    if c.addresses_recipient or (c.urgent and t.level is not TrustLevel.UNKNOWN):
        return _Verdict(Action.NOTIFY, MessageType.URGENT, "DIRECT_OR_URGENT", "Addresses the user directly or is time-sensitive, from a known sender.")


def _known_personal(m, t, c, d):
    if m.conversation_type is ConversationType.PERSONAL and t.level is TrustLevel.KNOWN_CONTACT:
        return _Verdict(Action.NOTIFY, MessageType.PERSONAL, "KNOWN_CONTACT", "Personal message from a known contact.")


def _unknown_sender(m, t, c, d):
    if t.level is TrustLevel.UNKNOWN:
        return _Verdict(Action.DIGEST, MessageType.UNKNOWN, "UNKNOWN_SENDER", "Sender is not known; low priority.")


def _default(m, t, c, d):
    return _Verdict(Action.DIGEST, MessageType.BUSINESS_UPDATE if m.conversation_type is ConversationType.BUSINESS else MessageType.PERSONAL, "DEFAULT", "Nothing time-critical; fine for the digest.")


# Precedence order. Safety first, then user preferences, then importance, then defaults.
RULES: tuple[_Rule, ...] = (
    _credential_request,
    _impersonation,
    _unknown_payment,
    _group_muted,
    _promotion,
    _broadcast,
    _trusted_payment,
    _schedule,
    _direct_address,
    _known_personal,
    _unknown_sender,
    _default,
)


def _is_actionable(c: Cues) -> bool:
    if c.promotional and not c.wants_payment:
        return False  # marketing is routed, never acted on
    return c.wants_payment or c.wants_secret or c.wants_schedule or c.wants_forward or c.asks_reply


def route(message: Message, trust: SenderTrust, dataset: Dataset) -> RoutingDecision:
    """Decide notify/digest/mute and whether the agent loop should run."""
    cues = extract_cues(message.message_text, message.user_id)
    verdict = next(v for rule in RULES if (v := rule(message, trust, cues, dataset)) is not None)
    fired = [name for name, on in cues.model_dump().items() if on]
    return RoutingDecision(
        action=verdict.action,
        message_type=verdict.message_type,
        rule=verdict.rule,
        reason=verdict.reason,
        actionable=_is_actionable(cues),
        cues=cues,
        signals=fired,
    )
