"""Content-hash cache for LLM responses (adapted from the old media/perception cache).

Key = sha256 of the canonical request (provider, model, thinking setting, messages, tools).
Same request, same answer: re-runs are instant and a live demo is deterministic. Entries are
JSON files under ``<cache_dir>/llm/ab/<key>.json``; a corrupt entry is treated as a miss.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

CACHE_SCHEMA_VERSION = 1


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_key(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class ContentCache:
    def __init__(self, root: Path, namespace: str = "llm", read_only_fallbacks: tuple[Path, ...] = ()) -> None:
        """``read_only_fallbacks`` are extra roots consulted on a miss (e.g. the committed demo
        fixture). Writes only ever go to ``root``."""
        self._dir = Path(root) / namespace
        self._fallbacks = tuple(Path(p) / namespace for p in read_only_fallbacks)

    def _path(self, key: str, base: Path | None = None) -> Path:
        return (base or self._dir) / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        for base in (self._dir, *self._fallbacks):
            value = self._read(self._path(key, base), key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _read(path: Path, key: str) -> dict[str, Any] | None:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or entry.get("key") != key or entry.get("schema") != CACHE_SCHEMA_VERSION:
            return None
        value = entry.get("value")
        return value if isinstance(value, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"schema": CACHE_SCHEMA_VERSION, "key": key, "value": value}
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(canonical_json(entry))
            os.replace(tmp, path)  # atomic: a concurrent reader never sees a half-written entry
        except OSError:
            Path(tmp).unlink(missing_ok=True)

    def clear(self) -> int:
        removed = 0
        for f in self._dir.glob("*/*.json"):
            f.unlink(missing_ok=True)
            removed += 1
        return removed
