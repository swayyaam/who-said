"""Per-user context: a learned engagement profile plus explicit preferences.

This package is pure: it depends only on the core schemas and the lexical cues. It must not
import the agent, the tools, the store, the LLM layer or the router (a test enforces that),
so nothing an agent does can reach it except through the two sanctioned write paths:
user events (``LearnedProfile.record_event``) and the explicit preferences API.
"""

from whosaid.profile.entities import entities_of
from whosaid.profile.learned import EntityScore, LearnedProfile, ProfileBook, engagement_signal
from whosaid.profile.params import ProfileParams
from whosaid.profile.preferences import (
    InMemoryPreferenceReader,
    PreferenceError,
    PreferenceReader,
    Preferences,
    apply_update,
    dnd_active,
)
from whosaid.profile.seed import seed_book

__all__ = [
    "EntityScore", "InMemoryPreferenceReader", "LearnedProfile", "PreferenceError", "PreferenceReader",
    "Preferences", "ProfileBook", "ProfileParams", "apply_update", "dnd_active", "engagement_signal",
    "entities_of", "seed_book",
]
