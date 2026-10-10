"""The channel-agnostic trust interface, and the registry that picks a provider."""

from __future__ import annotations

from typing import Protocol

from whosaid.errors import ConfigError
from whosaid.ingest.dataset import Dataset
from whosaid.schemas import Channel, Message, SenderTrust


class TrustProvider(Protocol):
    """Turns a message into a verdict on who sent it. Pure: same data, same answer."""

    channel: Channel

    def assess(self, message: Message) -> SenderTrust: ...


def get_trust_provider(channel: Channel, dataset: Dataset) -> TrustProvider:
    # Imported here so adding a channel is one new module plus one line below.
    if channel is Channel.WHATSAPP:
        from whosaid.trust.whatsapp import WhatsAppTrustProvider

        return WhatsAppTrustProvider(dataset)
    raise ConfigError(f"no trust provider for channel {channel!r}")
