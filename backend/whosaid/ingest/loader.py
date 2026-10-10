"""Read, validate and index a dataset of CSVs (bundled, on disk, or uploaded).

Generalised from an earlier project's loader to take a mapping of
``filename -> bytes`` so an upload goes through exactly the same path as a folder.
Every problem found is collected and reported together in one ``DatasetError``.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from pydantic import ValidationError

from whosaid.errors import DatasetError
from whosaid.ingest.dataset import Dataset
from whosaid.schemas import (
    BusinessProfile,
    BusinessRelationship,
    ConversationType,
    GroupProfile,
    MediaDescription,
    Membership,
    Message,
    RegisteredPayee,
    Row,
    ScenarioLabel,
    UserProfile,
)

MAX_PROBLEMS_PER_FILE = 10

# file stem -> (row model, required?)
FILE_SPECS: dict[str, tuple[type[Row], bool]] = {
    "messages": (Message, True),
    "users": (UserProfile, True),
    "groups": (GroupProfile, True),
    "group_members": (Membership, True),
    "business_accounts": (BusinessProfile, True),
    "user_business_history": (BusinessRelationship, True),
    "message_history": (Message, True),
    "registered_payees": (RegisteredPayee, False),
    "scenario_labels": (ScenarioLabel, False),
    "media_descriptions": (MediaDescription, False),
}
# Part of the original schema; accepted but not needed by WhoSaid.
IGNORED_FILES = {"message_events", "images", "voice_notes", "daily_notification_summary", "sample_messages", "output"}


def _required_columns(model: type[Row]) -> list[str]:
    return [name for name, f in model.model_fields.items() if f.is_required()]


def _stem(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.lower().endswith(".csv") else name


def _parse_file(stem: str, raw: bytes, model: type[Row], problems: list[str]) -> list[Row]:
    label = f"{stem}.csv"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        problems.append(f"{label}: not valid UTF-8 text")
        return []
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = [c.strip() for c in (reader.fieldnames or [])]
    missing = [c for c in _required_columns(model) if c not in columns]
    if missing:
        problems.append(f"{label}: missing required column(s) {missing}; found {columns}")
        return []
    rows: list[Row] = []
    bad = 0
    for line_no, cells in enumerate(reader, start=2):
        cleaned = {(k or "").strip(): v for k, v in cells.items()}
        try:
            rows.append(model.model_validate(cleaned))
        except ValidationError as exc:
            bad += 1
            if bad <= MAX_PROBLEMS_PER_FILE:
                first = exc.errors()[0]
                field = ".".join(str(p) for p in first["loc"])
                problems.append(f"{label} line {line_no}: {field}: {first['msg']}")
    if bad > MAX_PROBLEMS_PER_FILE:
        problems.append(f"{label}: {bad - MAX_PROBLEMS_PER_FILE} more invalid row(s) not shown")
    return rows


def _check_references(
    messages: list[Message],
    users: dict,
    groups: dict,
    memberships: dict,
    businesses: dict,
    problems: list[str],
) -> None:
    seen: set[str] = set()
    for m in messages:
        where = f"messages.csv {m.message_id}"
        if m.message_id in seen:
            problems.append(f"{where}: duplicate message_id")
        seen.add(m.message_id)
        if m.user_id not in users:
            problems.append(f"{where}: user_id {m.user_id!r} is not in users.csv")
        if m.conversation_type is ConversationType.GROUP:
            if not m.group_id or m.group_id not in groups:
                problems.append(f"{where}: group_id {m.group_id!r} is not in groups.csv")
            elif (m.group_id, m.user_id) not in memberships:
                problems.append(f"{where}: user {m.user_id!r} is not a member of {m.group_id!r}")
            if not m.sender_user_id:
                problems.append(f"{where}: group message has no sender_user_id")
        elif m.conversation_type is ConversationType.BUSINESS:
            if not m.business_id or m.business_id not in businesses:
                problems.append(f"{where}: business_id {m.business_id!r} is not in business_accounts.csv")
        elif not m.sender_user_id:
            problems.append(f"{where}: personal message has no sender_user_id")


def load_dataset_files(files: Mapping[str, bytes], *, name: str = "dataset") -> Dataset:
    """Validate and index ``filename -> bytes``. Raises DatasetError listing every problem."""
    by_stem = {_stem(fn): raw for fn, raw in files.items()}
    problems: list[str] = []
    parsed: dict[str, list[Row]] = {}

    for stem, (model, required) in FILE_SPECS.items():
        raw = by_stem.get(stem)
        if raw is None:
            if required:
                problems.append(f"{stem}.csv: required file is missing")
            parsed[stem] = []
            continue
        parsed[stem] = _parse_file(stem, raw, model, problems)

    if "messages" in by_stem and not parsed["messages"] and not any("messages.csv" in p for p in problems):
        problems.append("messages.csv: contains no data rows")

    users = {u.user_id: u for u in parsed["users"]}  # type: ignore[attr-defined]
    groups = {g.group_id: g for g in parsed["groups"]}  # type: ignore[attr-defined]
    memberships = {(m.group_id, m.user_id): m for m in parsed["group_members"]}  # type: ignore[attr-defined]
    businesses = {b.business_id: b for b in parsed["business_accounts"]}  # type: ignore[attr-defined]
    relationships = {(r.user_id, r.business_id): r for r in parsed["user_business_history"]}  # type: ignore[attr-defined]
    messages: list[Message] = parsed["messages"]  # type: ignore[assignment]
    history: list[Message] = parsed["message_history"]  # type: ignore[assignment]

    _check_references(messages, users, groups, memberships, businesses, problems)
    for h in history:
        if h.user_id not in users:
            problems.append(f"message_history.csv {h.message_id}: user_id {h.user_id!r} is not in users.csv")
            break

    labels = {l.message_id: l for l in parsed["scenario_labels"]}  # type: ignore[attr-defined]
    known_ids = {m.message_id for m in messages}
    for label_id in labels:
        if label_id not in known_ids:
            problems.append(f"scenario_labels.csv: {label_id!r} is not a message_id in messages.csv")

    if problems:
        raise DatasetError(f"dataset {name!r} is invalid ({len(problems)} problem(s))", problems)

    payees = {(p.owner_type, p.owner_id): p for p in parsed["registered_payees"]}  # type: ignore[attr-defined]
    media = {d.media_id: d for d in parsed["media_descriptions"]}  # type: ignore[attr-defined]
    by_user: dict[str, list[Message]] = defaultdict(list)
    for h in sorted(history, key=lambda r: r.created_at):
        by_user[h.user_id].append(h)

    digest = hashlib.sha256()
    for stem in sorted(by_stem):
        digest.update(stem.encode())
        digest.update(by_stem[stem])
    used = tuple(sorted(s for s in by_stem if s in FILE_SPECS or s in IGNORED_FILES))

    return Dataset(
        dataset_id=digest.hexdigest()[:12],
        name=name,
        files=used,
        messages=tuple(messages),
        history=tuple(history),
        users=users,
        groups=groups,
        memberships=memberships,
        businesses=businesses,
        relationships=relationships,
        payees=payees,
        labels=labels,
        media=media,
        history_by_user={u: tuple(rows) for u, rows in by_user.items()},
    )


def load_dataset_dir(directory: Path, *, name: str | None = None) -> Dataset:
    """Load every ``*.csv`` in a folder."""
    directory = Path(directory)
    if not directory.is_dir():
        raise DatasetError(f"dataset folder not found: {directory}")
    files = {p.name: p.read_bytes() for p in sorted(directory.glob("*.csv"))}
    if not files:
        raise DatasetError(f"no .csv files in {directory}")
    return load_dataset_files(files, name=name or directory.name)
