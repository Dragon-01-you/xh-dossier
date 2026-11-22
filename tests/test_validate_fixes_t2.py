#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #2 regressions: cliché bypass and impossible calendar dates."""

import importlib.util
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("validate_kit_t2", SCRIPTS / "03_validate_kit.py")
vk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vk)

KIT_NAMES = list(vk.REQUIRED_KIT_FILES)


def make_kit(tmp_path: pathlib.Path, extra_by_file: dict[str, str] | None = None) -> pathlib.Path:
    for name in KIT_NAMES:
        (tmp_path / name).write_text(
            f"# {name}\n\n这是一份足够长的正常档案内容，用于通过最短长度检查。" * 3,
            encoding="utf-8",
        )
    for name, extra in (extra_by_file or {}).items():
        path = tmp_path / name
        path.write_text(path.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
    return tmp_path


def test_cliche_in_rule_description_is_not_exempt(tmp_path: pathlib.Path) -> None:
    # Old bug: a line containing 禁止 was skipped wholesale.
    kit = make_kit(tmp_path, {"AGENTS.md": "我们禁止说这是一个非常好的问题这种水话。"})
    ok, diags = vk.validate_kit(kit)
    assert ok is False
    assert any("CLICHE" in d for d in diags), diags


def test_quoted_cliche_example_adjacent_to_rule_is_allowed(tmp_path: pathlib.Path) -> None:
    kit = make_kit(tmp_path, {"AGENTS.md": "禁用水话：“这是一个非常好的问题”这类。"})
    ok, diags = vk.validate_kit(kit)
    assert ok is True, diags


def test_distant_banned_word_does_not_exempt_quote(tmp_path: pathlib.Path) -> None:
    # Review E4: “...” 这是禁止的腔调 must still fail; verb is not adjacent.
    kit = make_kit(tmp_path, {"AGENTS.md": "“这是一个非常好的问题”这是禁止的腔调。"})
    ok, diags = vk.validate_kit(kit)
    assert ok is False
    assert any("CLICHE" in d for d in diags), diags


def test_all_chinese_quote_styles_can_be_rule_examples(tmp_path: pathlib.Path) -> None:
    for open_q, close_q in (("‘", "’"), ("《", "》"), ("「", "」"), ("『", "』"), ("〈", "〉")):
        kit = make_kit(tmp_path, {"AGENTS.md": f"禁止说{open_q}这是一个非常好的问题{close_q}这类水话。"})
        ok, diags = vk.validate_kit(kit)
        assert ok is True, (open_q, diags)


def test_impossible_calendar_date_fails(tmp_path: pathlib.Path) -> None:
    kit = make_kit(tmp_path, {"01-身份与当前主线.md": "- 事件日期：2025-02-30"})
    ok, diags = vk.validate_kit(kit)
    assert ok is False
    assert any("INVALID_DATE" in d and "2025-02-30" in d for d in diags), diags


def test_valid_calendar_date_passes(tmp_path: pathlib.Path) -> None:
    kit = make_kit(tmp_path, {"01-身份与当前主线.md": "- 事件日期：2024-02-29"})
    ok, diags = vk.validate_kit(kit)
    assert ok is True, diags


def test_month_only_date_is_not_treated_as_impossible(tmp_path: pathlib.Path) -> None:
    kit = make_kit(tmp_path, {"01-身份与当前主线.md": "- 月份：2025-02"})
    ok, diags = vk.validate_kit(kit)
    assert ok is True, diags
