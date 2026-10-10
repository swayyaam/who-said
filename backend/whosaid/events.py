"""Progress events. ``Emitter`` is how the pipeline and agent loop report what they do.

Phase b prints events in the CLI; the SSE stream (phase d) is another Emitter feeding a bus.
"""

from __future__ import annotations

from typing import Any, Callable

from whosaid.schemas import EventType

# (event type, message id or None, data)
Emitter = Callable[[EventType, "str | None", dict[str, Any]], None]


def noop_emit(_type: EventType, _message_id: str | None, _data: dict[str, Any]) -> None:
    return None
