#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #10: separate EVENT time (T) from MENTION time (T').

User pain: "When I tell an AI what I did BEFORE, the system marks the time as the
day I said it, then treats it as something I DID that day." Their knowledge base
(03-hard-rules:12) already has the rule: retrospective markers => mark event_date
as [记忆, 待核] and verify against original evidence.

This module detects retrospective statements so the ingest layer can store:
  created_at = when the line was said/exported  (T', transaction time)
  event_date = when the event actually happened (T, valid time) or [待核]
  date_kind  = stated | retrospective | unknown
"""

from __future__ import annotations

import re
from typing import Literal

DateKind = Literal["stated", "retrospective", "unknown"]

# Retrospective markers: the event happened BEFORE the moment of speaking.
RETROSPECTIVE_MARKERS = [
    r"以前", r"之前", r"早先", r"原先", r"当初", r"当时", r"那会", r"那时候", r"那年",
    r"上周", r"上个月", r"去年", r"前年", r"大一", r"大二", r"大三", r"小时候",
    r"记得", r"回想", r"想起来", r"曾经", r"一度",
]
RETRO_RE = re.compile("|".join(RETROSPECTIVE_MARKERS))

# Explicit stated-now markers (event is at/after mention time).
NOW_MARKERS = ["今天", "刚才", "刚刚", "现在", "这周", "本周", "这次", "目前"]
UNVERIFIED = "[记忆，待核]"


def detect_event_time(content: str, mention_date: str) -> tuple[str, DateKind, str | None]:
    """Return (event_date, date_kind, matched_marker).

    - mention_date is created_at (T'), the day the line was said/exported.
    - If retrospective marker found: event_date = UNVERIFIED, kind = retrospective.
    - If an explicit absolute date appears alongside a retrospective marker,
      use that date as a tentative event_date but still flag retrospective.
    - Otherwise: event_date = mention_date, kind = stated.
    """
    if not content:
        return mention_date, "unknown", None

    match = RETRO_RE.search(content)
    if not match:
        return mention_date, "stated", None

    marker = match.group(0)
    # A concrete date in the same sentence can anchor the real event time.
    abs_date = re.search(r"(20\d{2})[-年/](\d{1,2})?[-月/]?(\d{1,2})?", content)
    if abs_date:
        y = int(abs_date.group(1))
        mo = int(abs_date.group(2) or 1)
        d = int(abs_date.group(3) or 1)
        # Guardrail: real data contains stray numbers like "2025-20-26" (a version
        # string, not a date). Reject impossible calendar values instead of storing
        # a fake event date — fall back to [待核] which is honest.
        if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}", "retrospective", marker
        return UNVERIFIED, "retrospective", marker

    return UNVERIFIED, "retrospective", marker


def needs_verification(event_date: str) -> bool:
    return UNVERIFIED in event_date
