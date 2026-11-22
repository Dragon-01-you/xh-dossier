#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #10: event time vs mention time separation."""

import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from event_time import UNVERIFIED, detect_event_time, needs_verification  # noqa: E402


def test_plain_statement_uses_mention_date():
    event, kind, marker = detect_event_time("今天我开工先定了验收标准", "2026-11-22")
    assert event == "2026-11-22"
    assert kind == "stated"
    assert marker is None


def test_retrospective_marker_flagged_unverified():
    event, kind, marker = detect_event_time("大一那会我做过一个校园卡项目", "2026-11-22")
    assert event == UNVERIFIED
    assert kind == "retrospective"
    assert marker is not None


def test_retrospective_with_absolute_date_anchors_tentative():
    event, kind, _ = detect_event_time("记得 2025-09 我砍掉了闲鱼副业", "2026-11-22")
    assert event == "2025-09-01"
    assert kind == "retrospective"


def test_上周_is_retrospective():
    event, kind, _ = detect_event_time("上周聊Python自动化那个AI记错了我的方向", "2026-11-22")
    assert kind == "retrospective"
    assert event == UNVERIFIED


def test_empty_content_is_unknown():
    event, kind, marker = detect_event_time("", "2026-11-22")
    assert kind == "unknown"
    assert marker is None


def test_needs_verification():
    assert needs_verification(UNVERIFIED) is True
    assert needs_verification("2025-09-01") is False


def test_invalid_calendar_date_not_stored_as_event_date():
    # Real data had "2025-20-26" (a stray version-like number). Must not become a date.
    event, kind, _ = detect_event_time("记得 2025-20-26 那版，后来改了", "2026-11-22")
    assert event == UNVERIFIED
    assert kind == "retrospective"
