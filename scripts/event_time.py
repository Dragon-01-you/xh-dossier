#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #10: separate EVENT time (T) from MENTION time (T').

User pain: "When I tell an AI what I did BEFORE, the system marks the time as the
day I said it, then treats it as something I DID that day." Their knowledge base
(03-hard-rules:12) already has the rule: retrospective statements => mark
event_date as [记忆，待核] and verify against original evidence.

Stores:
  created_at = when the line was said/exported   (T', transaction time)
  event_date = when the event actually happened  (T, valid time) or [记忆，待核]
  date_kind  = stated | retrospective | retrospective_month | unknown

Hardened after independent code review (2026-11-22): real calendar validation,
paired-delimiter dates only, imperative "记得" no longer misclassified, explicit
now-markers win, month precision is never fabricated into a day.
"""

from __future__ import annotations

import calendar
import datetime
import re
from typing import Literal

DateKind = Literal["stated", "retrospective", "retrospective_month", "unknown"]

UNVERIFIED = "[记忆，待核]"

# Strong retrospective markers: unambiguously a past event.
_STRONG_RETRO = [
    r"以前", r"早先", r"原先", r"当初", r"那时候", r"那年",
    r"上周", r"上个月", r"去年", r"前年", r"大一", r"大二", r"大三", r"小时候",
    r"回想", r"想起来", r"曾经", r"一度", r"那次", r"那回",
]
# Ambiguous markers: "记得/之前/当时/那会" can be imperative or vague.
# They only count as retrospective when paired with a past cue in the SAME clause.
_AMBIGUOUS_RETRO = [r"记得", r"之前", r"当时", r"那会"]
_PAST_CUES = [r"那", r"过", r"了", r"曾", r"以前", r"之前", r"当初", r"当时", r"回", r"上次", r"去年", r"上周"]

# Explicit "now" markers: the event is at mention time; these WIN over retro cues.
NOW_MARKERS = ["今天", "刚才", "刚刚", "现在", "这周", "本周", "这次", "目前", "正在"]

# An absolute date must have PAIRED delimiters: 2025-09, 2025年09月, 2025/09/01.
# This avoids slicing a version number like "2025-123" into 2025-12-03.
_FULL_DATE_RE = re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")
_MONTH_DATE_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})(?:月)?(?![\d\-/])")
_CJK_FULL_DATE_RE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")

_CLAUSE_SPLIT_RE = re.compile(r"[。！？；;\n]")


def _valid_calendar_date(y: int, mo: int, d: int) -> bool:
    """Real calendar validation — rejects 2025-02-30, unlike a naive range check."""
    if not (2000 <= y <= 2100 and 1 <= mo <= 12):
        return False
    if not (1 <= d <= calendar.monthrange(y, mo)[1]):
        return False
    try:
        datetime.date(y, mo, d)
        return True
    except ValueError:
        return False


def _clauses(content: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT_RE.split(content) if c.strip()]


def _clause_is_retrospective(clause: str) -> tuple[bool, str | None]:
    for pat in _STRONG_RETRO:
        if re.search(pat, clause):
            return True, pat
    for pat in _AMBIGUOUS_RETRO:
        if not re.search(pat, clause):
            continue
        # "记得当时..." / "记得 2025-..." = recall; "记得帮我看一下" = imperative.
        has_past_cue = any(re.search(cue, clause) for cue in _PAST_CUES)
        has_year = bool(re.search(r"20\d{2}", clause))
        if has_past_cue or has_year:
            return True, pat
    return False, None


def _find_anchored_date(clause: str) -> tuple[str | None, DateKind | None]:
    """Return (validated_date, precision_kind) or (None, None).

    Month precision stays month-level ("2025-09") — never fabricate a day.
    """
    # Scan ALL candidate dates in the clause and return the first VALID one.
    # If the first date is an invalid calendar date (e.g. 2025-02-30), keep looking
    # instead of giving up — a later valid date may be the real anchor.
    for m in _CJK_FULL_DATE_RE.finditer(clause):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_calendar_date(y, mo, d):
            return f"{y:04d}-{mo:02d}-{d:02d}", "retrospective"
    for m in _FULL_DATE_RE.finditer(clause):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_calendar_date(y, mo, d):
            return f"{y:04d}-{mo:02d}-{d:02d}", "retrospective"
    for m in _MONTH_DATE_RE.finditer(clause):
        y, mo = int(m.group(1)), int(m.group(2))
        if 2000 <= y <= 2100 and 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}", "retrospective_month"
    return None, None


def detect_event_time(content: str, mention_date: str) -> tuple[str, DateKind, str | None]:
    """Return (event_date, date_kind, matched_marker).

    Clause-level detection: only the clause containing a retrospective marker
    is judged retro; an explicit now-marker in that clause wins (stated).
    """
    if not content:
        return mention_date, "unknown", None

    for clause in _clauses(content):
        if any(now in clause for now in NOW_MARKERS):
            # A "today/now" clause is current — but do not let it override a
            # different retro clause; continue scanning other clauses.
            continue
        is_retro, marker = _clause_is_retrospective(clause)
        if not is_retro:
            continue
        anchored, precision = _find_anchored_date(clause)
        if anchored:
            return anchored, precision, marker  # type: ignore[return-value]
        return UNVERIFIED, "retrospective", marker

    return mention_date, "stated", None


def needs_verification(event_date: str) -> bool:
    return UNVERIFIED in event_date
