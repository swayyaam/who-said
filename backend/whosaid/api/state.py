from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from whosaid.api.backend import Backend
from whosaid.config import Settings
from whosaid.datasets import DatasetRegistry
from whosaid.events import EventBus
from whosaid.runs import RunStore


@dataclass
class AppState:
    """Everything the API holds. One instance per app, so there is no module-level mutable state."""

    settings: Settings
    backend: Backend
    datasets: DatasetRegistry
    runs: RunStore = field(default_factory=RunStore)
    bus: EventBus = field(default_factory=EventBus)
    # The tool server's store is shared, so runs execute one at a time; later ones wait their turn as "pending".
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    tasks: set[asyncio.Task] = field(default_factory=set)
