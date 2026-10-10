"""Sender trust: computed in code from data, per channel. Never by the LLM."""

from whosaid.trust.base import TrustProvider, get_trust_provider

__all__ = ["TrustProvider", "get_trust_provider"]
