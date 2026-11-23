#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #4 + #7: export guide names the real script, both scopes, Save As dialog."""

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
doc = (REPO / "docs" / "02-multi-platform-export.md").read_text(encoding="utf-8")
readme = (REPO / "README.md").read_text(encoding="utf-8")


def test_engine_vs_script_distinction():
    assert "引擎" in doc and "工人" in doc
    assert "只装引擎" in doc


def test_afterchat_named_with_greasyfork():
    assert "AfterChat" in doc
    assert "589622" in doc
    assert "greasyfork.org" in doc


def test_platform_decision_table():
    assert "按你要导出的平台选" in doc
    assert "#8113" in doc and "#5715" in doc


def test_two_export_scopes():
    assert "单个 `.md`" in doc and "`.zip`" in doc
    assert "对话列表页" in doc or "首页" in doc


def test_save_as_dialog_documented():
    assert "另存为" in doc
    assert "prompt_for_download" in doc or "下载前询问保存位置" in doc
    assert "Ctrl+J" in doc


def test_batch_confirmation_gate_documented():
    # Review major: Issue #7's core finding (hidden confirmation gate +
    # 331->56 progress reset) was missing from the first docs commit.
    assert "56/331" in doc
    assert "确认门" in doc
    assert "回退" in doc or "循环" in doc


def test_no_fixed_download_path_claimed():
    # The guide must NOT tell users exports land in a fixed directory.
    assert "D:\\AI上下文" not in doc
    assert "D:\\eage下载" not in doc


def test_workbuddy_coexistence_note_is_user_tested_not_official():
    """#62 closed as user-verified: a WorkBuddy coexistence note may appear only
    when marked as a 2026-11-23 user test record. It must read neither as an
    official compatibility declaration nor as an official install step."""
    for line in doc.splitlines():
        if "WorkBuddy" in line:
            assert "用户实测" in line and "2026-11-23" in line, line
            assert "非官方兼容声明" in line, line
            assert "安装步骤" in line and "不写入" in line, line


def test_readme_points_to_afterchat():
    assert "AfterChat" in readme
    assert "589622" in readme


def test_workbuddy_unverified_path_gated():
    """Review B1 (PR-41): the WorkBuddy "设置 → 智能体 → 电脑操控/浏览器操控" menu
    path has no first-hand evidence (no official doc URL, screenshot, or real operation
    record). Any future mention of that product/menu in the guide MUST carry the
    `UNVERIFIED` marker on the same line; otherwise it must not be written back as a
    confirmed step.
    """
    unverified_tokens = ["电脑操控", "浏览器操控"]
    for line in doc.splitlines():
        if any(tok in line for tok in unverified_tokens):
            assert "UNVERIFIED" in line, (
                f"未标注 UNVERIFIED 的 WorkBuddy 菜单指引被写回文档: {line.strip()}"
            )


def test_doc_warns_against_inapp_browser():
    # Issue #9 CP2: the guide must explicitly tell users not to use the desktop
    # client's built-in / in-app browser (IAB), which usually does not reuse the
    # local browser's login state.
    assert "内置浏览器" in doc or "自带浏览器" in doc or "IAB" in doc


def test_doc_has_switch_verification_step():
    # Issue #9 CP3: beyond the switch instructions, the guide needs a concrete
    # "how to confirm the switches are actually on" self-check step.
    assert "怎么确认" in doc
    assert "ScriptCat 管理器" in doc and "启用" in doc
