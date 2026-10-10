"""Lexical cues: what a message text appears to ask for.

Deliberately cheap and deterministic. Cues only decide routing and whether the agent loop
runs at all; they never grant permissions (that is trust, computed from data).
"""

from __future__ import annotations

import re

from whosaid.schemas import Cues

_UPI_ID = re.compile(r"\b[\w.\-]{2,}@[a-z]{2,}\b", re.IGNORECASE)
_AMOUNT = re.compile(r"(₹|\brs\.?|\binr)\s?\d", re.IGNORECASE)
_PAY_WORDS = re.compile(r"\b(pay|paid|payment|settle|clear|transfer|send money|due|dues|bill|invoice|maintenance|fees?|refund|charges?)\b", re.IGNORECASE)
_SECRET = re.compile(r"\b(otp|one[- ]time (password|code|pin)|verification code|login code|security code|\d[- ]digit (login |security )?code|passcode|cvv|pin|password)\b", re.IGNORECASE)
_TIME = re.compile(r"\b\d{1,2}([:.]\d{2})?\s?(am|pm)\b", re.IGNORECASE)
_WHEN = re.compile(r"\b(mon|tues?|wed(nes)?|thu(rs)?|fri|sat(ur)?|sun)(day)?\b|\b(tomorrow|tonight|today|this (weekend|evening))\b", re.IGNORECASE)
_EVENT = re.compile(r"\b(dinner|lunch|breakfast|coffee|meet|meeting|call|catch up|party|plan|trip|match|game|appointment|visit|come over|join)\b", re.IGNORECASE)
_ASKS = re.compile(r"\?\s*$|\b(let me know|please reply|reply|confirm|can you|could you|are you free|are you coming)\b", re.IGNORECASE)
_FORWARD = re.compile(r"\bforward\b", re.IGNORECASE)
_PROMO = re.compile(r"\b(sale|offer|discount|cashback|coupon|deal|% off|limited[- ]time|unsubscribe|reply stop|festive|flat \d+)\b", re.IGNORECASE)
_STANDING = re.compile(r"\b(from now on|going forward|standing instruction|auto[- ]?pay|auto[- ]?approve|always (pay|approve|accept|forward|reply|trust))\b", re.IGNORECASE)
_URGENT = re.compile(r"\b(urgent|immediately|asap|right now|tonight|within \d+ ?(min|hour)|by \d+ ?(am|pm)|today|last chance|final notice)\b", re.IGNORECASE)


def extract_cues(text: str, user_id: str) -> Cues:
    has_upi = bool(_UPI_ID.search(text))
    has_amount = bool(_AMOUNT.search(text))
    pay_word = bool(_PAY_WORDS.search(text))
    wants_payment = (has_upi and (pay_word or has_amount)) or (has_amount and pay_word)
    when = bool(_TIME.search(text) or _WHEN.search(text))
    return Cues(
        wants_payment=wants_payment,
        wants_secret=bool(_SECRET.search(text)),
        wants_schedule=when and bool(_EVENT.search(text)),
        asks_reply=bool(_ASKS.search(text)),
        wants_forward=bool(_FORWARD.search(text)),
        promotional=bool(_PROMO.search(text)),
        urgent=bool(_URGENT.search(text)),
        addresses_recipient=f"@{user_id}".lower() in text.lower(),
        sets_preference=bool(_STANDING.search(text)),
    )
