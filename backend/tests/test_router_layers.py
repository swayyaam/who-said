"""Router precedence: safety, then explicit preferences, then learned scores, then defaults."""

import pytest

from whosaid.profile import LearnedProfile, Preferences, ProfileParams, seed_book
from whosaid.router import RoutingContext, route
from whosaid.schemas import Action, MessageType


def decide(demo, trust_of, mid, prefs=None, learned=None):
    msg = next(m for m in demo.messages if m.message_id == mid)
    ctx = RoutingContext(preferences=prefs or Preferences(), learned=learned)
    return route(msg, trust_of(mid), demo, ctx)


@pytest.fixture()
def book(demo):
    return seed_book(demo.history, demo.events)


def test_defaults_when_there_is_no_context(demo, trust_of):
    r = decide(demo, trust_of, "msg_203")
    assert (r.action, r.driver, r.rule) == (Action.NOTIFY, "default", "TRUSTED_PAYMENT")


def test_learned_scores_nudge_the_default(demo, trust_of, book):
    mute = decide(demo, trust_of, "msg_114", learned=book.for_user("u_110"))     # surveys the user always dismisses
    assert (mute.action, mute.driver, mute.rule) == (Action.MUTE, "learned", "LEARNED_MUTE")
    assert mute.profile_signals and "b_107" in mute.profile_signals[0]
    up = decide(demo, trust_of, "msg_113", learned=book.for_user("u_109"))        # delivery updates the user always opens
    assert (up.action, up.driver) == (Action.NOTIFY, "learned")


def test_explicit_preference_overrides_learned_score(demo, trust_of, book):
    # Learned says mute surveys; the user explicitly never mutes that business: preference wins.
    prefs = Preferences(never_mute_businesses=["b_107"])
    r = decide(demo, trust_of, "msg_114", prefs=prefs, learned=book.for_user("u_110"))
    assert (r.action, r.driver, r.rule) == (Action.DIGEST, "preference", "NEVER_MUTE")


def test_explicit_preference_overrides_default_rules(demo, trust_of):
    base = decide(demo, trust_of, "msg_108")
    assert base.action is Action.MUTE and base.message_type is MessageType.FORWARD   # chain message
    r = decide(demo, trust_of, "msg_108", prefs=Preferences(never_mute_senders=["u_110"]))
    assert (r.action, r.driver) == (Action.DIGEST, "preference")


def test_no_promotions_preference_mutes_promotions(demo, trust_of):
    r = decide(demo, trust_of, "msg_111", prefs=Preferences(mute_promotions=True))
    assert (r.action, r.rule, r.driver) == (Action.MUTE, "NO_PROMOTIONS", "preference")


def test_dnd_downgrades_a_non_urgent_notify_and_a_preference_window_beats_the_data_window(demo, trust_of):
    r = decide(demo, trust_of, "msg_120", prefs=Preferences(dnd_window="23:00-07:00"))
    assert (r.action, r.driver, r.rule) == (Action.DIGEST, "preference", "DND")
    off = decide(demo, trust_of, "msg_120", prefs=Preferences(dnd_window="01:00-02:00"))
    assert off.action is Action.NOTIFY   # outside the explicit window: the data window (22:30-07:30) is overridden


def test_safety_cannot_be_overridden_by_any_preference_or_score(demo, trust_of, book):
    prefs = Preferences(never_mute_senders=["u_160"], never_mute_businesses=["b_103"], never_mute_groups=["g_104"])
    for mid in ("msg_201", "msg_202", "msg_121", "msg_210"):
        r = decide(demo, trust_of, mid, prefs=prefs, learned=book.for_user(next(m.user_id for m in demo.messages if m.message_id == mid)))
        assert r.action is Action.MUTE and r.driver == "safety", mid


def test_learned_never_overrides_a_mute_and_never_downgrades_a_payment(demo, trust_of):
    p = ProfileParams(min_evidence=1)
    learned = LearnedProfile("u_101", p)
    msg = next(m for m in demo.messages if m.message_id == "msg_203")
    from whosaid.schemas import MessageEvent
    learned.record_event(msg, MessageEvent(user_id="u_101", message_id="x", notification_dismissed=True, muted_after_message=True))
    r = decide(demo, trust_of, "msg_203", learned=learned)   # strongly negative learned score
    assert r.action is Action.NOTIFY  # money due is never quietly downgraded by a learned score


def test_group_level_scores_cannot_mute_a_sender_with_no_history_of_their_own(demo, trust_of):
    # u_103 is an admin in g_101, whose group score is dragged down by a spammy member.
    p = ProfileParams(min_evidence=1)
    learned = LearnedProfile("u_101", p)
    from whosaid.schemas import Message, MessageEvent
    spam = Message.model_validate(dict(message_id="s", user_id="u_101", conversation_type="group", group_id="g_101",
                                       sender_user_id="u_999", created_at="2026-07-01 10:00", message_text="fwd"))
    for i in range(5):
        learned.record_event(spam, MessageEvent(user_id="u_101", message_id=f"s{i}", notification_dismissed=True, muted_after_message=True))
    r = decide(demo, trust_of, "msg_106", learned=learned) if False else decide(demo, trust_of, "msg_101", learned=learned)
    assert r.action is not Action.MUTE
