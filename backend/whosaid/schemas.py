"""Every typed boundary in WhoSaid: dataset rows, trust, routing, tool calls, results, events.

Dataset-row models (``Message`` ... ``MediaDescription``) accept the raw string cells of a
CSV: blanks become None, ``0``/``1`` become bools, timestamps are parsed. The core (agent
loop, gateways, tools) reads only the channel-agnostic parts: ``Message.message_id``,
``user_id``, ``message_text``, plus ``SenderTrust`` and ``ToolCall``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# ==========================================================================
# Enums
# ==========================================================================


class Channel(StrEnum):
    WHATSAPP = "whatsapp"


class ConversationType(StrEnum):
    PERSONAL = "personal"
    GROUP = "group"
    BUSINESS = "business"


class MediaKind(StrEnum):
    NONE = ""
    IMAGE = "image"
    VOICE = "voice"


class MemberRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class DomainState(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNDETERMINED = "undetermined"


class TrustLevel(StrEnum):
    UNKNOWN = "unknown"
    KNOWN_CONTACT = "known_contact"
    GROUP_ADMIN = "group_admin"
    VERIFIED_BUSINESS = "verified_business"


class Action(StrEnum):
    NOTIFY = "notify"
    DIGEST = "digest"
    MUTE = "mute"


class MessageType(StrEnum):
    PERSONAL = "personal"
    URGENT = "urgent"
    EVENT = "event"
    PAYMENT = "payment"
    BUSINESS_UPDATE = "business_update"
    PROMOTION = "promotion"
    GREETING = "greeting"
    FORWARD = "forward"
    SPAM = "spam"
    SCAM = "scam"
    UNKNOWN = "unknown"


class Enforcement(StrEnum):
    ON = "on"
    OFF = "off"


class ScenarioKind(StrEnum):
    ATTACK = "attack"
    CONTROL = "control"
    BACKGROUND = "background"


# ==========================================================================
# CSV cell coercion
# ==========================================================================


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def _to_bool(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes"}:
            return True
        if text in {"0", "false", "no", ""}:
            return False
        raise ValueError(f"{value!r} is not 0 or 1")
    return value


def _to_media_kind(value: Any) -> Any:
    return MediaKind.NONE if value is None or (isinstance(value, str) and not value.strip()) else value


def _to_int_default0(value: Any) -> Any:
    return 0 if value is None or (isinstance(value, str) and not value.strip()) else value


OptStr = Annotated[str | None, BeforeValidator(_blank_to_none)]
OptDateTime = Annotated[datetime | None, BeforeValidator(_blank_to_none)]
OptFloat = Annotated[float | None, BeforeValidator(_blank_to_none)]
Bool01 = Annotated[bool, BeforeValidator(_to_bool)]
Count = Annotated[int, BeforeValidator(_to_int_default0), Field(ge=0)]


class Row(BaseModel):
    """Base for dataset rows: strip strings, ignore columns we do not use."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ==========================================================================
# Dataset rows
# ==========================================================================


class Message(Row):
    """One incoming message (a row of messages.csv, or of message_history.csv)."""

    message_id: str
    user_id: str
    conversation_type: ConversationType
    group_id: OptStr = None
    business_id: OptStr = None
    sender_user_id: OptStr = None
    created_at: datetime
    message_text: str = ""
    media_type: Annotated[MediaKind, BeforeValidator(_to_media_kind)] = MediaKind.NONE
    media_id: OptStr = None
    forwarded_count: Count = 0
    channel: Channel = Channel.WHATSAPP

    @property
    def sender_id(self) -> str | None:
        """Who sent it: the business for a business chat, otherwise the user."""
        return self.business_id if self.conversation_type is ConversationType.BUSINESS else self.sender_user_id


class UserProfile(Row):
    user_id: str
    do_not_disturb_window: str = ""
    messages_opened_30d: Count = 0
    messages_replied_30d: Count = 0
    notifications_dismissed_30d: Count = 0
    messages_reported_30d: Count = 0


class GroupProfile(Row):
    group_id: str
    group_name: str = ""
    group_type: str = ""
    member_count: Count = 0
    admin_count: Count = 0


class Membership(Row):
    group_id: str
    user_id: str
    role: MemberRole = MemberRole.MEMBER
    group_muted_by_user: Bool01 = False


class BusinessProfile(Row):
    business_id: str
    display_name: str = ""
    brand_name: str = ""
    category: str = ""
    verified: Bool01 = False
    official_domain: OptStr = None
    domain_used_by_sender: OptStr = None
    account_age_days: Count = 0
    user_reports_30d: Count = 0


class BusinessRelationship(Row):
    user_id: str
    business_id: str
    why_user_knows_account: str = ""
    allows_promotions: Bool01 = True
    promotions_opted_out_at: OptDateTime = None


class MessageEvent(Row):
    """How a user reacted to a past message (a row of message_events.csv)."""

    user_id: str
    message_id: str
    message_opened: Bool01 = False
    message_replied: Bool01 = False
    reaction_time_minutes: OptFloat = None
    notification_dismissed: Bool01 = False
    muted_after_message: Bool01 = False
    message_reported: Bool01 = False


class PreferenceRow(Row):
    """One explicit preference, as a row of user_preferences.csv: user_id, key, value."""

    user_id: str
    key: str
    value: str = ""


class RegisteredPayee(Row):
    """The one UPI ID a group or business is known to collect payments at."""

    owner_type: str  # group | business | user
    owner_id: str
    upi_id: str
    label: str = ""


class ScenarioLabel(Row):
    """Demo/evaluation labels for a message: which tool calls would be harmful."""

    message_id: str
    scenario: str = ""
    kind: ScenarioKind = ScenarioKind.BACKGROUND
    expected_tools: str = ""  # ';'-joined tools a control message should lead to
    harmful_tools: str = ""  # ';'-joined tools that are harmful if executed for this message
    note: str = ""

    @property
    def expected(self) -> list[str]:
        return [t for t in self.expected_tools.split(";") if t]

    @property
    def harmful(self) -> list[str]:
        return [t for t in self.harmful_tools.split(";") if t]


class MediaDescription(Row):
    """A pre-computed description of an image/voice note (no vision model is called)."""

    media_id: str
    kind: str = ""
    description: str


# ==========================================================================
# Trust and routing
# ==========================================================================


class Sender(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: Channel
    sender_id: str
    kind: str  # user | business
    display_name: str = ""


class SenderTrust(BaseModel):
    """Who sent the message, how far to trust them, and the facts that say why.

    Computed in code from data. The LLM neither sees nor sets any of it.
    """

    sender: Sender
    level: TrustLevel
    signals: dict[str, bool | str | int | None] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    registered_payee: str | None = None
    has_relationship: bool = False
    # The receiving user's existing contacts: the only people a forward may go to.
    allowed_recipients: list[str] = Field(default_factory=list)


class Cues(BaseModel):
    """What the message text appears to ask for. Cheap lexical cues, not understanding."""

    wants_payment: bool = False
    wants_secret: bool = False
    wants_schedule: bool = False
    asks_reply: bool = False
    wants_forward: bool = False
    promotional: bool = False
    urgent: bool = False
    addresses_recipient: bool = False
    sets_preference: bool = False  # tries to install a standing instruction ("from now on always ...")


class RoutingDecision(BaseModel):
    action: Action
    message_type: MessageType
    rule: str
    reason: str
    actionable: bool
    cues: Cues
    signals: list[str] = Field(default_factory=list)
    # What decided it, in order of precedence: safety, preference (explicit), learned, default.
    driver: str = "default"
    driver_detail: str = ""
    profile_signals: list[str] = Field(default_factory=list)  # learned scores that were considered


# ==========================================================================
# Tool calls and authorization
# ==========================================================================


class ToolCall(BaseModel):
    """One tool call the agent wants to make.

    ``model_args`` come from the LLM. ``trusted_args`` are injected by code from data.
    ``arguments`` merges them with the trusted values winning, so a model can never
    override a trusted parameter even if it tries.
    """

    tool: str
    model_args: dict[str, Any] = Field(default_factory=dict)
    trusted_args: dict[str, Any] = Field(default_factory=dict)

    @property
    def arguments(self) -> dict[str, Any]:
        return {**self.model_args, **self.trusted_args}


class DecisionLayer(StrEnum):
    """Which AgntID layer made a decision. NONE means no layer was involved (enforcement off, or an
    allowed call that no layer objected to)."""

    NONE = "none"
    PROFILE = "profile"  # the tool is not exposed by the runtime's protection profile
    POLICY = "policy"  # a per-tool policy (Rego or input constraints) denied the call
    INTENT = "intent"  # the intent check found the call does not match the task


class AuthzDecision(BaseModel):
    allowed: bool
    tool: str
    reason: str
    source: str  # "direct" (no enforcement) | "agntid" | "agent"
    enforced: bool
    layer: DecisionLayer = DecisionLayer.NONE
    policy: str | None = None
    code: str | None = None


class ToolAttempt(BaseModel):
    """A tool call, the authorization decision on it, and what happened."""

    call: ToolCall
    decision: AuthzDecision
    executed: bool = False
    result: dict[str, Any] | None = None
    money_moved_inr: float = 0.0
    harmful: bool = False


class AgentTrace(BaseModel):
    ran: bool = False
    attempts: list[ToolAttempt] = Field(default_factory=list)
    final_text: str = ""
    turns: int = 0
    llm_calls: int = 0
    llm_cache_hits: int = 0
    latency_ms: float = 0.0
    error: str | None = None


# ==========================================================================
# Results, summaries, events
# ==========================================================================


class MessageResult(BaseModel):
    message_id: str
    user_id: str
    text: str
    sender: Sender
    trust: SenderTrust
    routing: RoutingDecision
    scenario: ScenarioLabel | None = None
    agent: AgentTrace = Field(default_factory=AgentTrace)
    executed_tools: list[str] = Field(default_factory=list)
    money_moved_inr: float = 0.0
    harmful_executed: list[str] = Field(default_factory=list)
    harmful_money_lost_inr: float = 0.0
    legit_actions_ok: bool | None = None  # control messages only
    denials_by_layer: dict[str, int] = Field(default_factory=dict)  # profile / policy / intent, this message only


class TrustBreakdown(BaseModel):
    messages: int = 0
    attempted: int = 0
    allowed: int = 0
    denied: int = 0
    executed: int = 0
    harmful_executed: int = 0


class RunSummary(BaseModel):
    run_id: str = ""
    dataset_id: str = ""
    enforcement: Enforcement
    model: str = ""
    messages: int = 0
    by_action: dict[str, int] = Field(default_factory=dict)
    agent_runs: int = 0
    actions_attempted: int = 0
    actions_allowed: int = 0
    actions_denied: int = 0
    actions_executed: int = 0
    harmful_executed: int = 0
    harmful_money_lost_inr: float = 0.0
    total_money_moved_inr: float = 0.0
    denials_by_layer: dict[str, int] = Field(default_factory=dict)  # profile / policy / intent
    preference_changes_executed: int = 0  # update_preferences calls that actually ran
    by_driver: dict[str, int] = Field(default_factory=dict)  # how many decisions each layer drove
    controls_total: int = 0
    controls_ok: int = 0
    by_trust_level: dict[str, TrustBreakdown] = Field(default_factory=dict)


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    MESSAGE_STARTED = "message.started"
    MESSAGE_ROUTED = "message.routed"
    AGENT_STEP = "agent.step"
    TOOL_ATTEMPTED = "tool.attempted"
    AUTHZ_DECISION = "authz.decision"
    TOOL_EXECUTED = "tool.executed"
    MESSAGE_COMPLETED = "message.completed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class RunEvent(BaseModel):
    """One progress event. The SSE stream sends these verbatim as JSON."""

    run_id: str
    seq: int = 0
    type: EventType
    message_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
