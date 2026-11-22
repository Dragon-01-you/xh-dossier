#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #2: validator bypass + strict/[待确认] conflict."""

import importlib.util
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("validate_kit", SCRIPTS / "03_validate_kit.py")
vk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vk)

KIT_NAMES = [
    "AGENTS.md", "00-总入口索引.md", "01-身份与当前主线.md",
    "02-核心判断准则.md", "03-硬规则与表达黑话.md", "04-正反例避坑账.md",
]


def make_kit(tmp_path, extra_by_file=None):
    for name in KIT_NAMES:
        (tmp_path / name).write_text("# " + name + "\n\n这是一份足够长的正常档案内容，用于通过最短长度检查。" * 3, encoding="utf-8")
    for name, extra in (extra_by_file or {}).items():
        p = tmp_path / name
        p.write_text(p.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
    return tmp_path


def test_cliche_in_rule_description_no_longer_bypasses(tmp_path):
    # Bug A: "禁止说'这是一个非常好的问题'" used to be skipped entirely.
    kit = make_kit(tmp_path, {"AGENTS.md": "我们禁止说这是一个非常好的问题这种水话。"})
    ok, diags = vk.validate_kit(kit)
    assert ok is False
    assert any("CLICHE" in d for d in diags), diags


def test_quoted_cliche_example_is_allowed(tmp_path):
    # A real rule listing the banned phrase inside quotes should be allowed.
    kit = make_kit(tmp_path, {"AGENTS.md": "禁用水话：“这是一个非常好的问题”这类。"})
    ok, diags = vk.validate_kit(kit)
    assert ok is True, diags


def test_strict_does_not_fail_on_dai_que_ren(tmp_path):
    # Bug B: SKILL.md requires marking uncertain facts [待确认]; strict must not fail on it.
    kit = make_kit(tmp_path, {"04-正反例避坑账.md": "某件事细节记不清，标 [待确认] 留待回填。"})
    ok, diags = vk.validate_kit(kit, strict=True)
    assert ok is True, diags
    assert any("INFO" in d and "待确认" in d for d in diags), diags


def test_natural_language_uncertainty_gets_warning(tmp_path):
    # Bug C: "记不清/待核实" in prose used to be invisible; now warned (not failed).
    kit = make_kit(tmp_path, {"01-身份与当前主线.md": "这件事的具体日期记不清了，待核实。"})
    ok, diags = vk.validate_kit(kit, strict=False)
    assert ok is True
    assert any("UNCERTAIN_PROSE" in d for d in diags), diags


def test_real_cliche_still_fails(tmp_path):
    kit = make_kit(tmp_path, {"AGENTS.md": "这是一个非常好的问题，我们从多维度赋能。"})
    ok, diags = vk.validate_kit(kit)
    assert ok is False
    assert sum(1 for d in diags if "CLICHE" in d) >= 1
