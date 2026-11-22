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


def test_no_fixed_download_path_claimed():
    # The guide must NOT tell users exports land in a fixed directory.
    assert "D:\\AI上下文" not in doc
    assert "D:\\eage下载" not in doc


def test_readme_points_to_afterchat():
    assert "AfterChat" in readme
    assert "589622" in readme
