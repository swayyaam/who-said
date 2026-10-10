"""notify / digest / mute triage, plus the "should the agent act on this?" flag.

Precedence, highest first:
  1. safety           scams and impersonation are muted no matter what anyone prefers or has learned
  2. explicit         the user's stated preferences (muted groups, no promotions, never-mute lists,
                      do-not-disturb) override everything below them
  3. learned          engagement scores from the user's own reactions nudge the default
  4. default rules    deterministic rules over trust and message cues

``RoutingDecision.driver`` names the layer that decided. ``actionable`` is independent of the
action: a scam asking for an OTP is muted *and* actionable, because an agent with tools could
still be talked into acting on it. Messages with nothing to act on skip the LLM entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from whosaid.cues import extract_cues
from whosaid.ingest.dataset import Dataset
from whosaid.profile import LearnedProfile, Preferences, ProfileParams, dnd_active
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


@dataclass(frozen=True)
class RoutingContext:
    """Per-user context for a routing decision: explicit preferences and the learned profile."""

    preferences: Preferences = field(default_factory=Preferences)
    learned: LearnedProfile | None = None
    params: ProfileParams = field(default_factory=ProfileParams)


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


def _preference_tampering(m, t, c, d):
    if c.sets_preference and t.level is TrustLevel.UNKNOWN:
        return _Verdict(Action.MUTE, MessageType.SCAM, "PREFERENCE_TAMPERING", "A stranger is trying to install a standing instruction for your account.")


# Layer 1: safety. Nothing a user prefers or has learned can un-mute these.
SAFETY_RULES: tuple[_Rule, ...] = (_credential_request, _impersonation, _unknown_payment, _preference_tampering)

# Layer 4: default rules, in order. (The group-mute flag is an explicit preference, handled above.)
DEFAULT_RULES: tuple[_Rule, ...] = (
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
    return c.wants_payment or c.wants_secret or c.wants_schedule or c.wants_forward or c.asks_reply or c.sets_preference


def _first(rules: tuple[_Rule, ...], m: Message, t: SenderTrust, c: Cues, d: Dataset) -> _Verdict | None:
    return next((v for rule in rules if (v := rule(m, t, c, d)) is not None), None)


def _sender_entity(m: Message, t: SenderTrust) -> tuple[str, str]:
    """(kind, id) for never-mute lookups: the business for a business chat, else the user."""
    return ("business", t.sender.sender_id) if m.conversation_type is ConversationType.BUSINESS else ("sender", t.sender.sender_id)


def _never_muted(m: Message, t: SenderTrust, prefs: Preferences) -> str | None:
    kind, sid = _sender_entity(m, t)
    if kind == "sender" and sid in prefs.never_mute_senders:
        return f"never mute sender {sid}"
    if kind == "business" and sid in prefs.never_mute_businesses:
        return f"never mute business {sid}"
    if m.group_id and m.group_id in prefs.never_mute_groups:
        return f"never mute group {m.group_id}"
    return None


def _explicit_decision(m: Message, t: SenderTrust, c: Cues, d: Dataset, ctx: RoutingContext) -> _Verdict | None:
    """Explicit preferences that decide outright (before defaults and learned scores)."""
    prefs = ctx.preferences
    never = _never_muted(m, t, prefs)
    membership = d.membership(m.group_id, m.user_id)
    if membership is not None and membership.group_muted_by_user and not c.addresses_recipient and never is None:
        return _Verdict(Action.MUTE, MessageType.UNKNOWN, "GROUP_MUTED", "You muted this group and the message does not address you directly.")
    if prefs.mute_promotions and c.promotional and not c.wants_payment and never is None:
        return _Verdict(Action.MUTE, MessageType.PROMOTION, "NO_PROMOTIONS", "You asked not to receive promotions.")
    return None


def _learned_adjust(base: _Verdict, m: Message, ctx: RoutingContext) -> tuple[_Verdict, list[str]]:
    """Nudge the default using the user's own engagement history. Never touches a mute."""
    if ctx.learned is None:
        return base, []
    seen = ctx.learned.strongest(m)
    notes = [f"{k.value} {eid}: {s.score:+.2f} over {s.n} interaction(s)" for k, eid, s in seen]
    if not seen or base.action is Action.MUTE:
        return base, notes
    kind, eid, s = seen[0]
    specific = kind.value in ("sender", "business")  # a group or category score must not speak for one sender
    p = ctx.params
    why = f"{kind.value} {eid} engagement {s.score:+.2f} over {s.n} interaction(s)"
    if base.action is Action.NOTIFY and s.score <= p.downgrade_below and base.message_type is not MessageType.PAYMENT:
        return _Verdict(Action.DIGEST, base.message_type, "LEARNED_DOWNGRADE", f"You usually ignore this ({why})."), notes
    if base.action is Action.DIGEST and specific and s.score <= p.mute_below:
        return _Verdict(Action.MUTE, base.message_type, "LEARNED_MUTE", f"You consistently dismiss this ({why})."), notes
    if base.action is Action.DIGEST and specific and s.score >= p.upgrade_above and base.message_type is not MessageType.PROMOTION:
        return _Verdict(Action.NOTIFY, base.message_type, "LEARNED_UPGRADE", f"You usually engage with this ({why})."), notes
    return base, notes


def _explicit_modify(v: _Verdict, m: Message, t: SenderTrust, c: Cues, d: Dataset, ctx: RoutingContext) -> _Verdict | None:
    """Explicit preferences that adjust a finished verdict: never-mute and do-not-disturb."""
    if v.action is Action.MUTE and v.message_type not in (MessageType.SCAM, MessageType.SPAM):
        held = _never_muted(m, t, ctx.preferences)
        if held:
            return _Verdict(Action.DIGEST, v.message_type, "NEVER_MUTE", f"You asked to {held}.")
    if v.action is Action.NOTIFY:
        user = d.users.get(m.user_id)
        window = ctx.preferences.dnd_window or (user.do_not_disturb_window if user else "")
        if dnd_active(window, m.created_at) and not (c.urgent and t.level is not TrustLevel.UNKNOWN):
            return _Verdict(Action.DIGEST, v.message_type, "DND", f"Do-not-disturb ({window}); not urgent from someone you know.")
    return None


def route(message: Message, trust: SenderTrust, dataset: Dataset, ctx: RoutingContext | None = None) -> RoutingDecision:
    """Decide notify/digest/mute and whether the agent loop should run."""
    ctx = ctx or RoutingContext()
    cues = extract_cues(message.message_text, message.user_id)
    fired = [name for name, on in cues.model_dump().items() if on]
    actionable = _is_actionable(cues)

    def decision(v: _Verdict, driver: str, detail: str, notes: list[str]) -> RoutingDecision:
        return RoutingDecision(action=v.action, message_type=v.message_type, rule=v.rule, reason=v.reason,
                               actionable=actionable, cues=cues, signals=fired, driver=driver,
                               driver_detail=detail, profile_signals=notes)

    safety = _first(SAFETY_RULES, message, trust, cues, dataset)
    if safety is not None:
        return decision(safety, "safety", safety.reason, [])

    explicit = _explicit_decision(message, trust, cues, dataset, ctx)
    if explicit is not None:
        return decision(explicit, "preference", explicit.reason, [])

    base = _first(DEFAULT_RULES, message, trust, cues, dataset)
    assert base is not None  # _default always matches
    learned, notes = _learned_adjust(base, message, ctx)
    verdict, driver = learned, ("learned" if learned is not base else "default")

    adjusted = _explicit_modify(verdict, message, trust, cues, dataset, ctx)
    if adjusted is not None:
        verdict, driver = adjusted, "preference"
    return decision(verdict, driver, verdict.reason, notes)
