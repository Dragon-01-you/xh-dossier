# -*- coding: utf-8 -*-
"""Validator compatibility with real-world kits (issue #15 follow-up).

- Accept the real renamed 04 file alongside the canonical template name.
- Do not flag angle-bracket tokens inside inline backtick code as unfilled
  placeholders (they are runtime path variables, e.g. `.../<任务>/`).
"""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

mod_val = import_module("03_validate_kit")

BODY = "这是经过核实并亲口拍板的真实个人核心记录条目，用于测试验证完整性。" * 3
CANONICAL_04 = "04-正反例避坑账.md"
ALIAS_04 = "04-反面案例清单.md"


def _kit(tmp_path: pathlib.Path, file_name: str | None, extra_lines: dict[str, str] | None = None) -> pathlib.Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (kit / fname).write_text(f"# {fname}\n\n{BODY}\n", encoding="utf-8")
    (kit / "AGENTS.md").write_text(
        (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    if file_name is not None:
        # Write the chosen 04 name and remove the canonical sibling if it differs.
        (kit / file_name).write_text(f"# {file_name}\n\n{BODY}\n", encoding="utf-8")
        if file_name != CANONICAL_04:
            (kit / CANONICAL_04).unlink(missing_ok=True)
    else:
        # No 04 file at all.
        (kit / CANONICAL_04).unlink(missing_ok=True)
    for fname, line in (extra_lines or {}).items():
        (kit / fname).write_text(f"# {fname}\n\n{BODY}\n{line}\n", encoding="utf-8")
    return kit


def test_real_alias_04_passes_strict(tmp_path: pathlib.Path) -> None:
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, ALIAS_04), strict=True)
    assert ok, msgs
    assert not any("MISSING" in m for m in msgs)


def test_canonical_04_passes_strict(tmp_path: pathlib.Path) -> None:
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, CANONICAL_04), strict=True)
    assert ok, msgs
    assert not any("MISSING" in m for m in msgs)


def test_missing_04_fails(tmp_path: pathlib.Path) -> None:
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, None), strict=True)
    assert not ok
    assert any(m.startswith("MISSING required file: 04-") for m in msgs)


def test_inline_code_placeholder_is_not_flagged(tmp_path: pathlib.Path) -> None:
    # `<任务>` lives inside an inline backtick span: a runtime dir variable.
    line = "每次进入 `01-当前任务/<任务>/` 用 AI 协作，必须写清关键决策点。"
    kit = _kit(
        tmp_path,
        CANONICAL_04,
        {"00-总入口索引.md": line, "02-核心判断准则.md": line},
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs
    assert not any("UNFILLED placeholders" in m for m in msgs)


def test_bare_placeholder_still_flagged(tmp_path: pathlib.Path) -> None:
    # A real unfilled placeholder outside backticks must still be reported.
    line = "一句话写清你的底层动机：<你的名字>"
    kit = _kit(tmp_path, CANONICAL_04, {"01-身份与当前主线.md": line})
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert any("UNFILLED placeholders" in m and "<你的名字>" in m for m in msgs)
