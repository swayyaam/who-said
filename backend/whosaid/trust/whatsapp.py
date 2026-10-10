"""WhatsApp trust: group admin role, verified business, domain match, existing relationship.

Level rules (first match wins):
  verified_business  business chat; account verified, sending from its own official domain,
                     display name matches the brand it claims
  group_admin        group chat; the sender holds the admin role in that group
  known_contact      the sender has messaged this user before in a personal chat
  unknown            everything else (including any business that fails the checks above)

A registered payee is attached only at the two payment-capable levels. "Has a relationship"
means: the receiver shares the group with the admin, or has history with the business.
"""

from __future__ import annotations

from whosaid.ingest.dataset import Dataset
from whosaid.schemas import (
    BusinessProfile,
    Channel,
    ConversationType,
    DomainState,
    MemberRole,
    Message,
    Sender,
    SenderTrust,
    TrustLevel,
)


def _normalise_domain(domain: str) -> str:
    return domain.strip().lower().removeprefix("www.")


def domain_state(business: BusinessProfile) -> DomainState:
    """MATCH, MISMATCH, or UNDETERMINED when either domain is blank (absence is not proof)."""
    if not business.official_domain or not business.domain_used_by_sender:
        return DomainState.UNDETERMINED
    official = _normalise_domain(business.official_domain)
    used = _normalise_domain(business.domain_used_by_sender)
    if not official or not used:
        return DomainState.UNDETERMINED
    return DomainState.MATCH if official == used else DomainState.MISMATCH


def identity_consistent(business: BusinessProfile) -> bool:
    """Whether the display name matches the brand it claims to be."""
    return business.display_name.strip().casefold() == business.brand_name.strip().casefold()


class WhatsAppTrustProvider:
    channel = Channel.WHATSAPP

    def __init__(self, dataset: Dataset) -> None:
        self._ds = dataset

    def assess(self, message: Message) -> SenderTrust:
        if message.conversation_type is ConversationType.BUSINESS:
            trust = self._assess_business(message)
        elif message.conversation_type is ConversationType.GROUP:
            trust = self._assess_group(message)
        else:
            trust = self._assess_personal(message)
        return trust.model_copy(update={"allowed_recipients": self.contacts(message.user_id)})

    def contacts(self, user_id: str) -> list[str]:
        """The user's existing contacts: everyone who has chatted with them one-to-one before."""
        return sorted({
            h.sender_user_id
            for h in self._ds.history_by_user.get(user_id, ())
            if h.conversation_type is ConversationType.PERSONAL and h.sender_user_id
        })

    # ---- business ---------------------------------------------------------

    def _assess_business(self, message: Message) -> SenderTrust:
        biz = self._ds.businesses[message.business_id or ""]
        sender = Sender(channel=self.channel, sender_id=biz.business_id, kind="business", display_name=biz.display_name)
        dom = domain_state(biz)
        consistent = identity_consistent(biz)
        relationship = self._ds.relationship(message.user_id, biz.business_id)
        signals = {
            "verified": biz.verified,
            "domain_state": dom.value,
            "official_domain": biz.official_domain,
            "domain_used_by_sender": biz.domain_used_by_sender,
            "identity_consistent": consistent,
            "has_relationship": relationship is not None,
            "user_reports_30d": biz.user_reports_30d,
            "account_age_days": biz.account_age_days,
        }
        reasons: list[str] = []
        reasons.append("account is verified" if biz.verified else "account is NOT verified")
        if dom is DomainState.MISMATCH:
            reasons.append(f"sends from {biz.domain_used_by_sender}, not its official domain {biz.official_domain}")
        elif dom is DomainState.MATCH:
            reasons.append(f"sends from its official domain {biz.official_domain}")
        else:
            reasons.append("sending domain could not be checked")
        if not consistent:
            reasons.append(f"display name {biz.display_name!r} does not match brand {biz.brand_name!r}")
        reasons.append("user has a history with this business" if relationship else "user has no history with this business")

        trusted = biz.verified and dom is DomainState.MATCH and consistent
        level = TrustLevel.VERIFIED_BUSINESS if trusted else TrustLevel.UNKNOWN
        # A payee is only released to the policy layer for a trusted business the user already deals with.
        payee = self._ds.payee("business", biz.business_id) if trusted and relationship is not None else None
        return SenderTrust(
            sender=sender,
            level=level,
            signals=signals,
            reasons=reasons,
            registered_payee=payee.upi_id if payee else None,
            has_relationship=relationship is not None,
        )

    # ---- group ------------------------------------------------------------

    def _assess_group(self, message: Message) -> SenderTrust:
        sender_id = message.sender_user_id or ""
        group = self._ds.groups.get(message.group_id or "")
        sender = Sender(channel=self.channel, sender_id=sender_id, kind="user", display_name=sender_id)
        membership = self._ds.membership(message.group_id, sender_id)
        is_admin = membership is not None and membership.role is MemberRole.ADMIN
        prior = self._prior_personal_messages(message.user_id, sender_id)
        signals = {
            "group_admin": is_admin,
            "group_type": group.group_type if group else None,
            "sender_in_group": membership is not None,
            "prior_personal_messages": prior,
            "has_relationship": True,
        }
        reasons = [f"sender is an admin of {group.group_name!r}" if is_admin and group else "sender is not a group admin"]
        if is_admin:
            payee = self._ds.payee("group", message.group_id)
            reasons.append(
                f"group has a registered payee ({payee.upi_id})" if payee else "group has no registered payee"
            )
            return SenderTrust(
                sender=sender,
                level=TrustLevel.GROUP_ADMIN,
                signals=signals,
                reasons=reasons,
                registered_payee=payee.upi_id if payee else None,
                has_relationship=True,
            )
        level = TrustLevel.KNOWN_CONTACT if prior else TrustLevel.UNKNOWN
        reasons.append(f"{prior} earlier personal message(s) from this sender" if prior else "no earlier personal chat with this sender")
        return SenderTrust(sender=sender, level=level, signals=signals, reasons=reasons, has_relationship=False)

    # ---- personal ---------------------------------------------------------

    def _assess_personal(self, message: Message) -> SenderTrust:
        sender_id = message.sender_user_id or ""
        sender = Sender(channel=self.channel, sender_id=sender_id, kind="user", display_name=sender_id)
        prior = self._prior_personal_messages(message.user_id, sender_id)
        level = TrustLevel.KNOWN_CONTACT if prior else TrustLevel.UNKNOWN
        reasons = [f"{prior} earlier message(s) from this sender in a personal chat" if prior else "first contact: no earlier personal chat with this sender"]
        return SenderTrust(
            sender=sender,
            level=level,
            signals={"prior_personal_messages": prior},
            reasons=reasons,
            has_relationship=prior > 0,
        )

    def _prior_personal_messages(self, user_id: str, sender_id: str) -> int:
        return sum(
            1
            for h in self._ds.history_by_user.get(user_id, ())
            if h.conversation_type is ConversationType.PERSONAL and h.sender_user_id == sender_id
        )
