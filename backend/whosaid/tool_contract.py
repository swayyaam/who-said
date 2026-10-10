"""The contract between the agent and the tools, shared by both sides.

``TRUSTED_PARAMS`` are tool arguments that carry trust context. They exist in the MCP tool
schemas (so AgntID policies can inspect them) but are REMOVED from the schemas the LLM sees,
and the agent loop fills them from data after the model proposes a call. The model can
never set them.
"""

from __future__ import annotations

import copy
from typing import Any

TRUSTED_PARAMS: tuple[str, ...] = (
    "user_id",  # the receiving user
    "message_id",  # the message being acted on
    "sender_id",  # who sent it
    "sender_trust",  # TrustLevel value, computed in code
    "registered_payee",  # the sender's registered UPI ID, if any ("" when none)
    "paid_today_to_payee",  # decimal string: INR already paid by this user to this payee (from the ledger), the cumulative-limit input
    "allowed_recipients",  # comma-separated ids of the receiving user's existing contacts (the only valid forward targets)
)

# Parameters the AgntID runtime adds to every tool schema for its own bookkeeping (task id, approval, delegation).
# The model never sees or sets them; the SDK/gateway handles them.
PLATFORM_PREFIXES: tuple[str, ...] = ("agntid_", "_")


def is_platform_param(name: str) -> bool:
    return name.startswith(PLATFORM_PREFIXES)


TOOL_NAMES: tuple[str, ...] = (
    "reply",
    "forward_message",
    "create_calendar_event",
    "pay_upi",
    "read_otp_messages",
    "block_sender",
    "update_preferences",
)


def _clean_property(name: str, prop: dict[str, Any]) -> dict[str, Any]:
    """Make a property schema the same whether it came from our server or the AgntID runtime."""
    prop = dict(prop)
    if "anyOf" in prop:  # Optional[X] -> X
        non_null = [p for p in prop.pop("anyOf") if p.get("type") != "null"]
        if len(non_null) == 1:
            prop = {**non_null[0], **prop}
    prop.pop("title", None)
    if prop.get("default") is None:
        prop.pop("default", None)
    if prop.get("description") == name:
        prop.pop("description", None)
    return prop


def model_visible_input_schema(input_schema: dict[str, Any]) -> dict[str, Any]:
    """A tool's JSON schema with every trusted parameter removed, normalised for the model."""
    schema = copy.deepcopy(input_schema)
    props = {k: _clean_property(k, v) for k, v in schema.get("properties", {}).items() if k not in TRUSTED_PARAMS and not is_platform_param(k)}
    schema["properties"] = props
    schema.pop("title", None)
    schema["required"] = [r for r in schema.get("required", []) if r not in TRUSTED_PARAMS and not is_platform_param(r)]
    return schema


def strip_trusted(arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Drop any trusted parameter the model tried to supply. Returns (clean, dropped names)."""
    dropped = [k for k in arguments if k in TRUSTED_PARAMS or is_platform_param(k)]
    return {k: v for k, v in arguments.items() if k not in dropped}, dropped
