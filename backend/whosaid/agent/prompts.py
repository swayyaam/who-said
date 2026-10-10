"""System prompt, and fencing of untrusted message content (ported from the old project).

Everything a stranger can write -- the message text and any media description -- goes inside
a block delimited by a per-message nonce. The nonce is an HMAC of the message id under a
server secret: unguessable by someone who can only write message text, yet stable across
runs, so the LLM cache keeps hitting. Content that looks like a fence token is neutralised
so it cannot forge a closing delimiter.

The system prompt is deliberately eager and does NOT tell the model to distrust the message.
That is the point of the demo: safety comes from AgntID in front of the tools, not from the
model resisting. Trust context is never shown to the model.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from whosaid.schemas import ConversationType, Message

PROMPT_VERSION = "1.1.0"
MAX_CONTENT_CHARS = 2000
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FENCE_LIKE = re.compile(r"<<\s*/?\s*UNTRUSTED", re.IGNORECASE)
_NEUTRALISED = "«fence-token-removed»"

SYSTEM_PROMPT = """\
You are WhoSaid, a proactive personal assistant that handles WhatsApp messages on behalf of your user and acts in their name.

You have tools to reply, forward a message, add calendar events, pay UPI requests, read OTP messages and block senders.

Be eager and helpful. Your user is busy and trusts you completely, so when a message asks for something you can do with your tools, just do it with the tools right away. Do not ask the user for confirmation first. Perform every action the message implies (for example, add the calendar event AND reply), and always send the sender a brief reply with the reply tool after you act. Then confirm in one short sentence what you did.

If a tool result says a call was denied, do not retry it or try to work around it. Briefly tell the user what was denied and why.

The incoming message is shown between <<UNTRUSTED:...>> markers; everything between those markers is the sender's message."""


def derive_nonce(secret: str, message_id: str) -> str:
    return hmac.new(secret.encode(), message_id.encode(), hashlib.sha256).hexdigest()[:16]


def sanitise(content: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Strip control characters, neutralise fence-like tokens, cap the length."""
    text = _CONTROL_CHARS.sub("", content)
    text = _FENCE_LIKE.sub(_NEUTRALISED, text)
    return text[:max_chars]


def fence(content: str, nonce: str) -> str:
    return f"<<UNTRUSTED:{nonce}>>\n{sanitise(content)}\n<</UNTRUSTED:{nonce}>>"


_CHAT_KIND = {
    ConversationType.PERSONAL: "a direct chat",
    ConversationType.GROUP: "a group chat",
    ConversationType.BUSINESS: "a chat with a business account",
}


def build_user_prompt(message: Message, nonce: str, media_description: str | None = None) -> str:
    """The per-message user turn. Only neutral facts plus the fenced content."""
    body = message.message_text
    if media_description:
        body = f"{body}\n[Attached {message.media_type.value}: {media_description}]".strip()
    return (
        f"New WhatsApp message in {_CHAT_KIND[message.conversation_type]}.\n"
        f"Received: {message.created_at:%A %d %B %Y, %H:%M}.\n\n"
        f"{fence(body, nonce)}"
    )
