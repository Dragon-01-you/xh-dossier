# -*- coding: utf-8 -*-
"""Issue #15: `[待确认]` markers must carry a real, machine-checkable provenance.

The validator really opens the cited file under the kit root, checks the line is
in range, and compares the normalized quote against that line's actual text —
not just counting the token.
"""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

mod_val = import_module("03_validate_kit")

BODY = "这是经过核实并亲口拍板的真实个人核心记录条目，用于测试验证完整性。" * 3
ACCEPTED_QUOTE = "一直在做对讲，把配色之类的全部弄好"
ACCEPTED_FILE = "flomo快照_2026-10-25.md"
ACCEPTED_LINE = 61


def _write_source(kit: pathlib.Path, fname: str, line_count: int, quote_at: int, quote: str) -> None:
    lines = [
        f"导出记录第 {i} 行：占位内容用于凑出行号，保证引文落在指定行上。"
        for i in range(1, line_count + 1)
    ]
    lines[quote_at - 1] = f"用户：{quote}"
    target = kit / fname
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


def _kit(
    tmp_path: pathlib.Path,
    marker_by_file: dict[str, str],
    source_specs: list[tuple[str, int, int, str]] | None = None,
) -> pathlib.Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (kit / fname).write_text(f"# {fname}\n\n{BODY}\n", encoding="utf-8")
    (kit / "AGENTS.md").write_text(
        (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for fname, line in marker_by_file.items():
        (kit / fname).write_text(f"# {fname}\n\n{BODY}\n{line}\n", encoding="utf-8")
    for fname, count, at, quote in source_specs or []:
        _write_source(kit, fname, count, at, quote)
    return kit


def _accepted_marker(quote: str = ACCEPTED_QUOTE, ref: str = f"{ACCEPTED_FILE}:{ACCEPTED_LINE}") -> str:
    return f"[待确认] 「对讲」本意不明 ｜ 原文：「{quote}」 ｜ 出处：{ref}"


# --- Acceptance criteria from issue #15 -------------------------------------


def test_bare_marker_without_source_fails_strict(tmp_path: pathlib.Path) -> None:
    # Anti-example: no quote, no source -> must FAIL (PENDING_UNSOURCED).
    kit = _kit(tmp_path, {"02-核心判断准则.md": "- [待确认] 早年变现立场是否矛盾"})
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert any(m.startswith("PENDING_UNSOURCED: 02-核心判断准则.md:") for m in msgs)


def test_sourced_marker_with_real_file_passes_strict(tmp_path: pathlib.Path) -> None:
    # Pro-example: quote really appears on the cited line -> passes, only INFO.
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": f"- {_accepted_marker()}"},
        [(ACCEPTED_FILE, ACCEPTED_LINE, ACCEPTED_LINE, ACCEPTED_QUOTE)],
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs
    assert any("INFO:" in m and "compliant" in m for m in msgs)
    assert not any(m.startswith("PENDING_") for m in msgs)


# --- Citation existence checks ----------------------------------------------


def test_line_out_of_range_fails(tmp_path: pathlib.Path) -> None:
    # Source file has 10 lines; citation points at line 99 -> out of range.
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": f"- {_accepted_marker(ref=f'{ACCEPTED_FILE}:99')}"},
        [(ACCEPTED_FILE, 10, 1, ACCEPTED_QUOTE)],
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert any(m.startswith("PENDING_LINE_OUT_OF_RANGE: 02-核心判断准则.md:") for m in msgs)


def test_source_file_missing_fails(tmp_path: pathlib.Path) -> None:
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": f"- {_accepted_marker(ref='does-not-exist.md:1')}"},
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert any(m.startswith("PENDING_SOURCE_MISSING: 02-核心判断准则.md:") for m in msgs)


def test_quote_one_char_wrong_fails(tmp_path: pathlib.Path) -> None:
    wrong_quote = "一直在做对讲，把配色之类的全部弄坏"  # last verb: 弄好 -> 弄坏
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": f"- {_accepted_marker(quote=wrong_quote)}"},
        [(ACCEPTED_FILE, ACCEPTED_LINE, ACCEPTED_LINE, ACCEPTED_QUOTE)],
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert any(m.startswith("PENDING_QUOTE_MISMATCH: 02-核心判断准则.md:") for m in msgs)


def test_fullwidth_halfwidth_variation_passes(tmp_path: pathlib.Path) -> None:
    # Source line uses full-width parentheses; the quote uses half-width ones.
    source_line = "一直在做对讲，把配色之类的全部弄好（备注行）"
    quote = "一直在做对讲，把配色之类的全部弄好(备注行)"
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": f"- {_accepted_marker(quote=quote)}"},
        [(ACCEPTED_FILE, ACCEPTED_LINE, ACCEPTED_LINE, source_line)],
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs


def test_dotdot_path_traversal_fails(tmp_path: pathlib.Path) -> None:
    # `../` escapes the kit root -> rejected even if such a file existed outside.
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": f"- {_accepted_marker(ref='../secret.md:3')}"},
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert any(m.startswith("PENDING_SOURCE_TRAVERSAL: 02-核心判断准则.md:") for m in msgs)


def test_mixed_markers_are_reported_separately(tmp_path: pathlib.Path) -> None:
    # One compliant, one bare, one quote-mismatch in the same kit.
    compliant = _accepted_marker()
    bare = "- [待确认] 早年变现立场是否矛盾"
    mismatch = f"- {_accepted_marker(quote='一直在做对讲，把配色之类的全部弄坏')}"
    kit = _kit(
        tmp_path,
        {
            "02-核心判断准则.md": f"- {compliant}\n{bare}",
            "04-正反例避坑账.md": mismatch,
        },
        [(ACCEPTED_FILE, ACCEPTED_LINE, ACCEPTED_LINE, ACCEPTED_QUOTE)],
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert sum("INFO:" in m and "compliant" in m for m in msgs) == 1
    assert any(m.startswith("PENDING_UNSOURCED: 02-核心判断准则.md:") for m in msgs)
    assert any(m.startswith("PENDING_QUOTE_MISMATCH: 04-正反例避坑账.md:") for m in msgs)


# --- Existing tri-state exemptions retained ----------------------------------


def test_non_strict_unsourced_reports_but_passes(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path, {"02-核心判断准则.md": "- [待确认] 早年变现立场是否矛盾"})
    ok, msgs = mod_val.validate_kit(kit, strict=False)
    assert ok, msgs
    assert any("PENDING_UNSOURCED" in m for m in msgs)


def test_backticked_meta_reference_is_not_counted(tmp_path: pathlib.Path) -> None:
    line = "- `[待确认]` `这是测试用户填写的稳定事实，用于全流程验证。`"
    kit = _kit(tmp_path, {"04-正反例避坑账.md": line})
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs
    assert not any(m.startswith("PENDING_") for m in msgs)
    assert not any("INFO:" in m for m in msgs)


def test_fenced_code_block_meta_reference_is_not_counted(tmp_path: pathlib.Path) -> None:
    line = "```\n- [待确认] 裸标记但位于代码块内\n```"
    kit = _kit(tmp_path, {"02-核心判断准则.md": line})
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs
    assert not any(m.startswith("PENDING_") for m in msgs)


def test_half_source_marker_still_fails(tmp_path: pathlib.Path) -> None:
    # Only `原文` present, no `出处`: must be treated as unsourced (issue #15).
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": "- [待确认] 疑点 ｜ 原文：「一直在做对讲」"},
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert not ok
    assert any("PENDING_UNSOURCED" in m for m in msgs)


def test_compliant_marker_line_exempt_from_placeholder_check(tmp_path: pathlib.Path) -> None:
    # A compliant marker line must not be double-flagged as an unfilled placeholder.
    kit = _kit(
        tmp_path,
        {"02-核心判断准则.md": f"- {_accepted_marker()}"},
        [(ACCEPTED_FILE, ACCEPTED_LINE, ACCEPTED_LINE, ACCEPTED_QUOTE)],
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs
    assert not any("UNFILLED placeholders" in m for m in msgs)
