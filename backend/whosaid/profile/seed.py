"""Cold start: build every user's profile in one pass over their history and reactions."""

from __future__ import annotations

from typing import Iterable, Mapping

from whosaid.profile.learned import ProfileBook
from whosaid.profile.params import ProfileParams
from whosaid.schemas import Message, MessageEvent


def seed_book(
    history: Iterable[Message],
    events: Mapping[tuple[str, str], MessageEvent],
    params: ProfileParams | None = None,
) -> ProfileBook:
    """Replay past messages in time order, applying each recorded reaction.

    A brand-new user therefore starts with a useful profile instead of an empty one.
    History rows with no recorded reaction are skipped: no event, no evidence.
    """
    book = ProfileBook(params)
    for message in sorted(history, key=lambda m: m.created_at):
        event = events.get((message.user_id, message.message_id))
        if event is not None:
            book.for_user(message.user_id).record_event(message, event)
    return book
