from __future__ import annotations

from whosaid.mcp_server.tools._common import finish
from whosaid.store import Store


def create_calendar_event(store: Store, *, title: str, start: str, user_id: str, message_id: str, sender_id: str, **_ignored) -> dict:
    """Add an event to the user's calendar."""
    result = store.add_event(user_id, title, start)
    return finish(store, tool="create_calendar_event", user_id=user_id, message_id=message_id, sender_id=sender_id, status="ok", result=result)
