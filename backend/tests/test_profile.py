"""The profile package: learning, cold start, preferences, and its isolation from the agent."""

import ast
from datetime import datetime
from pathlib import Path

import pytest

import whosaid.profile as profile_pkg
from whosaid.profile import (LearnedProfile, PreferenceError, Preferences, ProfileParams, apply_update, dnd_active,
                             engagement_signal, seed_book)
from whosaid.profile.entities import EntityKind, categorize, entities_of
from whosaid.profile.learned import EntityScore, next_score
from whosaid.schemas import Message, MessageEvent


def ev(**kw) -> MessageEvent:
    return MessageEvent(user_id="u", message_id="m", **kw)


def msg(mid="m1", **kw) -> Message:
    base = dict(message_id=mid, user_id="u", conversation_type="personal", sender_user_id="s1", created_at="2026-07-01 10:00", message_text="hello there")
    return Message.model_validate({**base, **kw})


def test_signals_are_ordered_and_bounded():
    assert engagement_signal(ev(message_replied=True, message_opened=True)) == 1.0  # clamped
    assert engagement_signal(ev(message_opened=True)) == pytest.approx(0.4)
    assert engagement_signal(ev(notification_dismissed=True)) == pytest.approx(-0.6)
    assert engagement_signal(ev(notification_dismissed=True, muted_after_message=True)) == -1.0
    assert engagement_signal(ev(message_reported=True)) == -1.0
    assert engagement_signal(ev()) == 0.0


def test_alpha_decays_then_floors_at_min_alpha():
    p = ProfileParams(min_alpha=0.1)
    s = EntityScore()
    s = next_score(s, 1.0, p)  # alpha = 1: the first event sets the score outright
    assert (s.score, s.n) == (1.0, 1)
    s = next_score(s, 0.0, p)  # alpha = 1/2
    assert s.score == pytest.approx(0.5)
    s = next_score(s, 0.0, p)  # alpha = 1/3
    assert s.score == pytest.approx(0.5 * 2 / 3)
    big = EntityScore(score=1.0, n=50)  # alpha would be 1/51 < MIN_ALPHA, so MIN_ALPHA applies
    assert next_score(big, 0.0, p).score == pytest.approx(0.9)


def test_scores_converge_but_keep_adapting():
    p = ProfileParams(min_alpha=0.2)
    s = EntityScore()
    for _ in range(40):
        s = next_score(s, 1.0, p)
    assert s.score == pytest.approx(1.0)
    for _ in range(10):  # behaviour changes: the score follows (a pure running mean would barely move)
        s = next_score(s, -1.0, p)
    assert s.score < 0.0


def test_entities_touched_by_a_message():
    m = msg(conversation_type="group", group_id="g1", message_text="Flat 40% off, shop now")
    kinds = [(k, i) for k, i in entities_of(m)]
    assert kinds == [(EntityKind.SENDER, "s1"), (EntityKind.GROUP, "g1"), (EntityKind.CATEGORY, "promotion")]
    b = msg(conversation_type="business", business_id="b1", sender_user_id=None)
    assert entities_of(b)[0] == (EntityKind.BUSINESS, "b1")
    assert categorize(msg(forwarded_count=9)) == "forward"


def test_record_event_updates_every_touched_entity():
    prof = LearnedProfile("u", ProfileParams())
    m = msg(conversation_type="group", group_id="g1")
    prof.record_event(m, ev(message_replied=True, message_opened=True))
    assert prof.get(EntityKind.SENDER, "s1").score == 1.0
    assert prof.get(EntityKind.GROUP, "g1").n == 1
    assert prof.get(EntityKind.SENDER, "nobody") is None


def test_one_event_is_not_enough_evidence_to_speak():
    prof = LearnedProfile("u", ProfileParams(min_evidence=2))
    prof.record_event(msg(), ev(notification_dismissed=True))
    assert prof.strongest(msg()) == []
    prof.record_event(msg("m2"), ev(notification_dismissed=True))
    assert prof.strongest(msg())[0][0] is EntityKind.SENDER


def test_cold_start_seeds_a_useful_profile_in_one_pass(demo):
    book = seed_book(demo.history, demo.events)
    quickbite = book.for_user("u_109").get(EntityKind.BUSINESS, "b_106")
    assert quickbite.n == 5 and quickbite.score > 0.6          # replies and opens
    stylehub = book.for_user("u_109").get(EntityKind.BUSINESS, "b_104")
    assert stylehub.score < -0.4                               # dismissed every time
    assert book.for_user("u_110").get(EntityKind.BUSINESS, "b_107").score <= -0.7
    assert "u_101" in book.users() and "u_999" not in book.users()


def test_history_without_a_recorded_reaction_is_skipped():
    book = seed_book([msg()], {})
    assert book.users() == []


# ---- explicit preferences ---------------------------------------------------------------------


def test_apply_update_list_bool_and_dnd():
    p = Preferences()
    p = apply_update(p, "never_mute_group", "g1")
    p = apply_update(p, "never_mute_group", "g1")  # idempotent
    p = apply_update(p, "never_mute_sender", "u9")
    p = apply_update(p, "mute_promotions", "true")
    p = apply_update(p, "dnd_window", "22:00-07:00")
    assert p.never_mute_groups == ["g1"] and p.never_mute_senders == ["u9"] and p.mute_promotions
    assert p.dnd_window == "22:00-07:00"
    p = apply_update(p, "never_mute_group", "remove:g1")
    assert p.never_mute_groups == []
    assert apply_update(p, "dnd_window", "").dnd_window is None


@pytest.mark.parametrize("key,value", [("nope", "x"), ("mute_promotions", "maybe"), ("dnd_window", "late"), ("never_mute_sender", "")])
def test_apply_update_rejects_bad_input(key, value):
    with pytest.raises(PreferenceError):
        apply_update(Preferences(), key, value)


def test_apply_update_does_not_mutate_its_input():
    p = Preferences()
    apply_update(p, "never_mute_group", "g1")
    assert p.never_mute_groups == []


@pytest.mark.parametrize("hour,minute,expected", [(23, 0, True), (2, 30, True), (6, 59, True), (7, 0, False), (12, 0, False), (22, 29, False)])
def test_dnd_window_crossing_midnight(hour, minute, expected):
    assert dnd_active("22:30-07:00", datetime(2026, 7, 1, hour, minute)) is expected


def test_dnd_same_day_window_and_empty():
    assert dnd_active("13:00-14:00", datetime(2026, 7, 1, 13, 30)) and not dnd_active("13:00-14:00", datetime(2026, 7, 1, 15, 0))
    assert not dnd_active(None, datetime(2026, 7, 1, 3, 0))


# ---- isolation ----------------------------------------------------------------------------------

FORBIDDEN = {"whosaid.agent", "whosaid.mcp_server", "whosaid.store", "whosaid.llm", "whosaid.pipeline", "whosaid.router",
             "whosaid.tool_contract", "whosaid.trust", "whosaid.ingest"}


def test_profile_package_does_not_depend_on_agent_tools_or_store():
    root = Path(profile_pkg.__file__).parent
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                assert not any(name == f or name.startswith(f + ".") for f in FORBIDDEN), f"{path.name} imports {name}"
