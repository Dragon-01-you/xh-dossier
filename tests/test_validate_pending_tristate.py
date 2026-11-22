# -*- coding: utf-8 -*-
"""CONFLICT-05: `[待确认]` strict tri-state (A compliant / B bare / C meta reference)."""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

mod_val = import_module("03_validate_kit")

BODY = "这是经过核实并亲口拍板的真实个人核心记录条目，用于测试验证完整性。" * 3
COMPLIANT = (
    "[待确认] 「对讲」本意不明 ｜ 原文：「一直在做对讲，把配色之类的全部弄好」 "
    "｜ 出处：flomo快照_2026-10-25.md:61"
)


def _kit(tmp_path: pathlib.Path, marker_line: str) -> pathlib.Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (kit / fname).write_text(f"# {fname}\n\n{BODY}\n", encoding="utf-8")
    (kit / "AGENTS.md").write_text(
        (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (kit / "02-核心判断准则.md").write_text(
        f"# 02\n\n{BODY}\n{marker_line}\n", encoding="utf-8"
    )
    return kit


def test_compliant_marker_is_info_and_passes_strict(tmp_path: pathlib.Path) -> None:
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, f"- {COMPLIANT}"), strict=True)
    assert ok, msgs
    assert any("INFO:" in m and "compliant" in m for m in msgs)
    assert not any("PENDING_UNTRACEABLE" in m for m in msgs)


def test_bare_marker_fails_strict_with_location(tmp_path: pathlib.Path) -> None:
    ok, msgs = mod_val.validate_kit(
        _kit(tmp_path, "- [待确认] 早年变现立场是否矛盾"), strict=True
    )
    assert not ok
    assert any(m.startswith("PENDING_UNTRACEABLE: 02-核心判断准则.md:") for m in msgs)


def test_bare_marker_is_info_only_in_non_strict(tmp_path: pathlib.Path) -> None:
    ok, msgs = mod_val.validate_kit(
        _kit(tmp_path, "- [待确认] 早年变现立场是否矛盾"), strict=False
    )
    assert ok, msgs
    # Bare markers are reported regardless of strict, but only strict fails.
    assert any("PENDING_UNTRACEABLE" in m for m in msgs)


def test_backticked_meta_reference_is_not_counted(tmp_path: pathlib.Path) -> None:
    line = "- `[待确认]` `这是测试用户填写的稳定事实，用于全流程验证。`"
    kit = _kit(tmp_path, line)
    (kit / "04-正反例避坑账.md").write_text(f"# 04\n\n{BODY}\n{line}\n", encoding="utf-8")
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs
    assert not any("PENDING_UNTRACEABLE" in m for m in msgs)
    assert not any("INFO:" in m for m in msgs)


def test_fenced_code_block_meta_reference_is_not_counted(tmp_path: pathlib.Path) -> None:
    line = "```\n- [待确认] 裸标记但位于代码块内\n```"
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, line), strict=True)
    assert ok, msgs
    assert not any("PENDING_UNTRACEABLE" in m for m in msgs)


def test_compliant_shape_line_exempt_from_placeholder_check(tmp_path: pathlib.Path) -> None:
    # The documented S2.4 shape uses `<疑点>` / `<file>:<line>`, which must not be
    # double-flagged as unfilled placeholders on an otherwise compliant marker.
    line = (
        "[待确认] <疑点> ｜ 原文：「<事件原文>」 ｜ 出处：<file>:<line>"
    )
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, f"- {line}"), strict=True)
    assert ok, msgs
    assert not any("UNFILLED placeholders" in m for m in msgs)


def test_half_source_marker_still_fails(tmp_path: pathlib.Path) -> None:
    # Only `原文` present, no `出处`: must be treated as bare (issue #15).
    ok, msgs = mod_val.validate_kit(
        _kit(tmp_path, "- [待确认] 疑点 ｜ 原文：「一直在做对讲」"), strict=True
    )
    assert not ok
    assert any("PENDING_UNTRACEABLE" in m for m in msgs)
