#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #1 + #3: deep-hook follow-up, language-following, custom options, unbundled choices."""

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
skill = (REPO / "skills" / "onboarding-interviewer" / "SKILL.md").read_text(encoding="utf-8")
prompt = (REPO / "prompts" / "01_web_ai_interviewer.md").read_text(encoding="utf-8")


def test_deep_hook_follow_up_in_skill():
    assert "深钩追问" in skill
    assert "带日期" in skill and "代价" in skill


def test_emotional_safety_framing():
    assert "情绪安全感" in skill and "说错不扣分" in skill


def test_language_following_in_both():
    assert "语言跟随" in skill
    assert "英文问→英文答" in prompt


def test_custom_option_in_both():
    assert "D` 自定义" in skill or "D 自定义" in skill
    assert "D 自定义位" in prompt


def test_q3_unbundled():
    # "不经同意改文件" and "AI 代做算能力" must be separate options.
    line_c = next(l for l in skill.splitlines() if l.strip().startswith("- `C` 不经本人同意"))
    line_d = next(l for l in skill.splitlines() if l.strip().startswith("- `D` 把 AI 代做"))
    assert "删改原文件" in line_c and "代做" not in line_c
    assert "代做成果" in line_d and "删改原文件" not in line_d
