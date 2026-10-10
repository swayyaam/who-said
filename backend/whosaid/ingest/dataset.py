"""The loaded dataset and its lookup indexes. A plain container: no I/O, no validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from whosaid.schemas import (
    BusinessProfile,
    BusinessRelationship,
    GroupProfile,
    MediaDescription,
    Membership,
    Message,
    RegisteredPayee,
    ScenarioLabel,
    UserProfile,
)


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    name: str
    files: tuple[str, ...]
    messages: tuple[Message, ...]
    history: tuple[Message, ...]
    users: dict[str, UserProfile]
    groups: dict[str, GroupProfile]
    memberships: dict[tuple[str, str], Membership]
    businesses: dict[str, BusinessProfile]
    relationships: dict[tuple[str, str], BusinessRelationship]
    payees: dict[tuple[str, str], RegisteredPayee]
    labels: dict[str, ScenarioLabel]
    media: dict[str, MediaDescription]
    history_by_user: dict[str, tuple[Message, ...]] = field(default_factory=dict)

    def membership(self, group_id: str | None, user_id: str | None) -> Membership | None:
        if group_id is None or user_id is None:
            return None
        return self.memberships.get((group_id, user_id))

    def relationship(self, user_id: str, business_id: str | None) -> BusinessRelationship | None:
        return None if business_id is None else self.relationships.get((user_id, business_id))

    def payee(self, owner_type: str, owner_id: str | None) -> RegisteredPayee | None:
        return None if owner_id is None else self.payees.get((owner_type, owner_id))
