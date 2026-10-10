"""A small error taxonomy, so a failure is classified instead of swallowed."""

from __future__ import annotations


class WhoSaidError(Exception):
    """Base class for every error this package raises on purpose."""


class DatasetError(WhoSaidError):
    """An uploaded or bundled dataset is missing files, columns, or valid values.

    ``problems`` carries every issue found, so the caller can show them all at once
    rather than one per attempt.
    """

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems = problems or [message]


class LLMError(WhoSaidError):
    """The model provider could not be reached or returned something unusable."""


class GatewayError(WhoSaidError):
    """The tool gateway (MCP client) could not reach its server."""


class ConfigError(WhoSaidError):
    """A setting is missing or invalid."""
