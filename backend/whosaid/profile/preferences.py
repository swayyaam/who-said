"""Explicit, user-stated preferences. They always override learned scores.

Stored separately from the learned profile. The only writers are the user (the preferences
API / CLI) and, for the demo's attack scenario, an MCP tool that an enforcement policy is
expected to deny whenever the call originates from an incoming message.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

# key -> (field name, kind). kind: "list" adds/removes an id, "bool" and "text" set a value.
PREFERENCE_KEYS: dict[str, tuple[str, str]] = {
    "never_mute_sender": ("never_mute_senders", "list"),
    "never_mute_group": ("never_mute_groups", "list"),
    "never_mute_business": ("never_mute_businesses", "list"),
    "mute_promotions": ("mute_promotions", "bool"),
    "dnd_window": ("dnd_window", "text"),
    "auto_pay_sender": ("auto_pay_senders", "list"),
}
_DND = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


class PreferenceError(ValueError):
    """An unknown key or an invalid value."""


class Preferences(BaseModel):
    never_mute_senders: list[str] = Field(default_factory=list)
    never_mute_groups: list[str] = Field(default_factory=list)
    never_mute_businesses: list[str] = Field(default_factory=list)
    mute_promotions: bool = False
    dnd_window: str | None = None  # "22:00-07:00"; None means use the window in the user's data
    # A recorded wish only. It never bypasses authorization: payments still need AgntID's allow.
    auto_pay_senders: list[str] = Field(default_factory=list)


def apply_update(prefs: Preferences, key: str, value: str) -> Preferences:
    """Return new preferences with one change applied. Raises PreferenceError when invalid.

    List keys take an id to add, or ``remove:<id>``. Bool keys take true/false. ``dnd_window``
    takes ``HH:MM-HH:MM`` or an empty value to clear.
    """
    if key not in PREFERENCE_KEYS:
        raise PreferenceError(f"unknown preference {key!r}; valid keys: {sorted(PREFERENCE_KEYS)}")
    field, kind = PREFERENCE_KEYS[key]
    value = (value or "").strip()
    data = prefs.model_copy(deep=True)
    if kind == "list":
        remove = value.lower().startswith("remove:")
        item = value[len("remove:"):].strip() if remove else value
        if not item:
            raise PreferenceError(f"{key} needs an id")
        current: list[str] = getattr(data, field)
        if remove:
            setattr(data, field, [x for x in current if x != item])
        elif item not in current:
            setattr(data, field, [*current, item])
    elif kind == "bool":
        if value.lower() not in {"true", "false", "1", "0", "yes", "no"}:
            raise PreferenceError(f"{key} must be true or false")
        setattr(data, field, value.lower() in {"true", "1", "yes"})
    else:
        if value and not _DND.match(value):
            raise PreferenceError("dnd_window must look like 22:00-07:00")
        setattr(data, field, value or None)
    return data


def dnd_active(window: str | None, at: datetime) -> bool:
    """Whether ``at`` falls inside a ``HH:MM-HH:MM`` window (which may cross midnight)."""
    if not window or not _DND.match(window):
        return False
    start_s, end_s = window.split("-")
    minutes = at.hour * 60 + at.minute
    start = int(start_s[:2]) * 60 + int(start_s[3:])
    end = int(end_s[:2]) * 60 + int(end_s[3:])
    return start <= minutes < end if start <= end else (minutes >= start or minutes < end)


class PreferenceReader(Protocol):
    """Where the router reads a user's explicit preferences from."""

    async def get(self, user_id: str) -> Preferences: ...


class InMemoryPreferenceReader:
    def __init__(self, preferences: dict[str, Preferences] | None = None) -> None:
        self._prefs = dict(preferences or {})

    async def get(self, user_id: str) -> Preferences:
        return self._prefs.get(user_id, Preferences())
