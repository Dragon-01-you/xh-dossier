#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #10 + review blockers: event time vs mention time, hardened."""

import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from event_time import UNVERIFIED, detect_event_time, needs_verification  # noqa: E402


def test_plain_statement_uses_mention_date():
    event, kind, marker = detect_event_time("今天我开工先定了验收标准", "2026-11-22")
    assert (event, kind, marker) == ("2026-11-22", "stated", None)


def test_generic_prose_is_not_an_event():
    # A work instruction is not a claim about when something happened. It must
    # NOT inherit created_at as event_date (that is the bug #10 fixes).
    event, kind, _ = detect_event_time("我觉得你可以深入看一下上面这些东西，这是我们的世界指南", "2026-11-22")
    assert event == "" and kind == "unknown"


def test_current_state_marker_is_not_an_event_date():
    # "目前/现在的目录" describes a state, not "I did X today"; it must not become T.
    for text in ("目前我们的世界指南是这版", "现在我们的目录里有这些资产"):
        event, kind, _ = detect_event_time(text, "2026-11-22")
        assert event == "" and kind == "unknown", (text, event, kind)


def test_now_with_completion_is_stated():
    event, kind, _ = detect_event_time("现在终于开工了", "2026-11-22")
    assert event == "2026-11-22" and kind == "stated"


def test_explicit_past_date_without_retro_word():
    event, kind, _ = detect_event_time("2025-09-20 我砍掉了闲鱼副业", "2026-11-22")
    assert event == "2025-09-20" and kind == "retrospective"


def test_explicit_today_date_is_stated():
    event, kind, _ = detect_event_time("2026-11-22 我先定了验收标准", "2026-11-22")
    assert event == "2026-11-22" and kind == "stated"


def test_retrospective_marker_flagged_unverified():
    event, kind, marker = detect_event_time("大一那会我做过一个校园卡项目", "2026-11-22")
    assert event == UNVERIFIED and kind == "retrospective" and marker is not None


def test_retrospective_with_full_date_anchors():
    event, kind, _ = detect_event_time("记得 2025-09-20 我砍掉了闲鱼副业", "2026-11-22")
    assert event == "2025-09-20" and kind == "retrospective"


def test_上周_is_retrospective():
    event, kind, _ = detect_event_time("上周聊Python自动化那个AI记错了我的方向", "2026-11-22")
    assert kind == "retrospective" and event == UNVERIFIED


def test_empty_content_is_unknown():
    assert detect_event_time("", "2026-11-22") == ("", "unknown", None)


def test_needs_verification():
    assert needs_verification(UNVERIFIED) is True
    assert needs_verification("2025-09-01") is False


# --- Review blocker regressions (E3) ---

def test_impossible_calendar_date_rejected():
    # 2025-02-30 does not exist — must NOT be stored as a fake event date.
    event, kind, _ = detect_event_time("记得 2025-02-30 那版，后来改了", "2026-11-22")
    assert event == UNVERIFIED
    assert kind in ("retrospective", "retrospective_month")


def test_version_number_not_parsed_as_date():
    event, _, _ = detect_event_time("记得 2025-123 这个版本号", "2026-11-22")
    assert event == UNVERIFIED
    assert "2025-12-03" not in event


def test_imperative_jide_not_retrospective():
    # "记得帮我..." / "请记得提交..." are imperatives, not recalled events.
    # They are not historical claims and should not inherit a fake event date.
    for text in ("记得帮我看一下这个文档", "请记得提交报告"):
        event, kind, _ = detect_event_time(text, "2026-11-22")
        assert kind == "unknown" and event == "", (text, event, kind)


def test_month_precision_not_fabricated_into_day():
    event, kind, _ = detect_event_time("记得 2025-09 我砍掉了闲鱼副业", "2026-11-22")
    assert event == "2025-09"
    assert kind == "retrospective_month"


def test_now_marker_wins_over_retro_cue():
    event, kind, _ = detect_event_time("之前一直没弄，现在终于开工了", "2026-11-22")
    assert kind == "stated" and event == "2026-11-22"


def test_multiple_dates_takes_validated_one():
    event, kind, _ = detect_event_time("记得 2025-02-30 和 2026-01-15 两次", "2026-11-22")
    assert event == "2026-01-15" and kind == "retrospective"


def test_cjk_full_date_validated():
    event, kind, _ = detect_event_time("记得 2025年9月20日 那次", "2026-11-22")
    assert event == "2025-09-20" and kind == "retrospective"


def test_descriptive_progressive_is_not_an_event():
    # "一座正在被续写的学院档案馆" is branding prose, not "I am doing X now".
    event, kind, _ = detect_event_time("芯火 · 档案纸，一座正在被续写的学院档案馆", "2026-09-02")
    assert event == "" and kind == "unknown"


def test_quoted_role_state_is_not_an_event():
    event, kind, _ = detect_event_time('模型不可自封"我现在是自动模式"', "2026-09-02")
    assert event == "" and kind == "unknown"


def test_third_person_today_is_not_an_event():
    event, kind, _ = detect_event_time("DailyExecution 当日执行：教师今天真正看到的表", "2026-09-02")
    assert event == "" and kind == "unknown"


def test_task_card_heading_is_not_an_event():
    event, kind, _ = detect_event_time("十一、本轮任务卡 · C0（第一轮，现在开始）", "2026-09-02")
    assert event == "" and kind == "unknown"


def test_ui_label_before_is_not_retrospective():
    event, kind, _ = detect_event_time("改之前看见代价：每笔 Proposal 带 costs 和人话", "2026-09-02")
    assert event == "" and kind == "unknown"
