from __future__ import annotations

from whosaid.mcp_server.tools._common import finish
from whosaid.store import Store


def reply(store: Store, *, text: str, user_id: str, message_id: str, sender_id: str, **_ignored) -> dict:
    """Send a reply to the person who sent the message being handled."""
    result = store.send(user_id, "reply", sender_id, text)
    return finish(store, tool="reply", user_id=user_id, message_id=message_id, sender_id=sender_id, status="ok", result=result)
