"""Progress events. ``Emitter`` is how the pipeline and agent loop report what they do.

Phase b prints events in the CLI; the SSE stream (phase d) is another Emitter feeding a bus.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from whosaid.schemas import EventType

# (event type, message id or None, data)
Emitter = Callable[[EventType, "str | None", dict[str, Any]], None]


def noop_emit(_type: EventType, _message_id: str | None, _data: dict[str, Any]) -> None:
    return None


class EventBus:
    """Per-run event log with live subscribers. Subscribers get every event from the start (replay), then live ones.

    The SSE endpoint is one subscriber; late joiners and reconnects see the full history. Not thread-safe:
    publish and subscribe from the event loop.
    """

    def __init__(self) -> None:
        self._events: dict[str, list] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._closed: set[str] = set()

    def publish(self, run_id: str, type_: EventType, message_id: str | None = None, data: dict[str, Any] | None = None):
        from whosaid.schemas import RunEvent

        log = self._events.setdefault(run_id, [])
        event = RunEvent(run_id=run_id, seq=len(log), type=type_, message_id=message_id, data=data or {})
        log.append(event)
        for q in self._queues.get(run_id, []):
            q.put_nowait(event)
        if type_ in (EventType.RUN_COMPLETED, EventType.RUN_FAILED):
            self.close(run_id)
        return event

    def close(self, run_id: str) -> None:
        self._closed.add(run_id)
        for q in self._queues.get(run_id, []):
            q.put_nowait(None)

    def history(self, run_id: str) -> list:
        return list(self._events.get(run_id, []))

    def connect(self, run_id: str, after_seq: int = -1):
        """Start a subscription. Returns (backlog, queue, finished).

        ``backlog`` is every event with seq > after_seq so far. ``queue`` receives later events, then ``None`` when the
        run closes. ``finished`` is True when the run had already closed (the backlog is then the whole story).
        """
        queue: asyncio.Queue = asyncio.Queue()
        backlog = [e for e in self._events.get(run_id, []) if e.seq > after_seq]
        finished = run_id in self._closed
        if not finished:
            self._queues.setdefault(run_id, []).append(queue)
        return backlog, queue, finished

    def disconnect(self, run_id: str, queue: asyncio.Queue) -> None:
        if queue in self._queues.get(run_id, []):
            self._queues[run_id].remove(queue)

    def drop(self, run_id: str) -> None:
        self._events.pop(run_id, None)
        self._queues.pop(run_id, None)
        self._closed.discard(run_id)
