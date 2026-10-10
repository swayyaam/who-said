"""The learned profile: one engagement score per entity, updated by user events.

score in [-1, 1]. Each event yields a signal in [-1, 1]; the score moves toward it by
``alpha = max(MIN_ALPHA, 1 / (n + 1))`` where n is how many interactions that entity has
already seen. The first event sets the score outright, the next few average, and after
~1/MIN_ALPHA events the score becomes an exponentially-weighted average, so it keeps adapting.
"""

from __future__ import annotations

from pydantic import BaseModel

from whosaid.profile.entities import EntityKind, SPECIFICITY, entities_of, entity_key
from whosaid.profile.params import ProfileParams
from whosaid.schemas import Message, MessageEvent


class EntityScore(BaseModel):
    score: float = 0.0
    n: int = 0


def engagement_signal(event: MessageEvent) -> float:
    """One interaction as a signal in [-1, 1]. Replying is the strongest positive, reporting the strongest negative."""
    raw = (
        1.0 * event.message_replied
        + 0.4 * event.message_opened
        - 0.6 * event.notification_dismissed
        - 0.9 * event.muted_after_message
        - 1.0 * event.message_reported
    )
    return max(-1.0, min(1.0, raw))


def next_score(current: EntityScore, signal: float, params: ProfileParams) -> EntityScore:
    alpha = max(params.min_alpha, 1.0 / (current.n + 1))
    return EntityScore(score=current.score + alpha * (signal - current.score), n=current.n + 1)


class LearnedProfile:
    """Scores for one receiving user."""

    def __init__(self, user_id: str, params: ProfileParams | None = None) -> None:
        self.user_id = user_id
        self._params = params or ProfileParams()
        self._scores: dict[str, EntityScore] = {}

    def get(self, kind: EntityKind, entity_id: str) -> EntityScore | None:
        return self._scores.get(entity_key(kind, entity_id))

    def record_event(self, message: Message, event: MessageEvent) -> None:
        """THE learning path: a user's reaction to a message updates every entity it touched."""
        signal = engagement_signal(event)
        for kind, entity_id in entities_of(message):
            key = entity_key(kind, entity_id)
            self._scores[key] = next_score(self._scores.get(key, EntityScore()), signal, self._params)

    def strongest(self, message: Message) -> list[tuple[EntityKind, str, EntityScore]]:
        """Scores with enough evidence for the entities this message touches, most specific first."""
        out = []
        for kind, entity_id in entities_of(message):
            s = self.get(kind, entity_id)
            if s is not None and s.n >= self._params.min_evidence:
                out.append((kind, entity_id, s))
        return sorted(out, key=lambda t: SPECIFICITY.index(t[0]))

    def snapshot(self) -> dict[str, EntityScore]:
        return dict(self._scores)


class ProfileBook:
    """Learned profiles for many users."""

    def __init__(self, params: ProfileParams | None = None) -> None:
        self.params = params or ProfileParams()
        self._profiles: dict[str, LearnedProfile] = {}

    def for_user(self, user_id: str) -> LearnedProfile:
        if user_id not in self._profiles:
            self._profiles[user_id] = LearnedProfile(user_id, self.params)
        return self._profiles[user_id]

    def users(self) -> list[str]:
        return sorted(self._profiles)
