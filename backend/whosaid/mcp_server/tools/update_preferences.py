from __future__ import annotations

from whosaid.mcp_server.tools._common import finish
from whosaid.profile.preferences import PreferenceError
from whosaid.store import Store


def update_preferences(store: Store, *, key: str, value: str, user_id: str, message_id: str, sender_id: str, **_ignored) -> dict:
    """Change one of the user's standing notification preferences."""
    try:
        prefs = store.update_preference(user_id, key, value)
    except PreferenceError as exc:
        return finish(store, tool="update_preferences", user_id=user_id, message_id=message_id, sender_id=sender_id,
                      status="error", result={"error": str(exc)})
    return finish(store, tool="update_preferences", user_id=user_id, message_id=message_id, sender_id=sender_id,
                  status="ok", result={"updated": {"key": key, "value": value}, "preferences": prefs.model_dump()})
