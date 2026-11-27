#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Safety tests for `08_l2_apply.py` after the independent code review.

These tests lock the behaviours that were previously only in prose:
- no anchor => safe stop, no write;
- AGENTS.md is read-only for the unsigned path;
- a legacy/partial pending zone is never duplicated;
- a full existing zone is an idempotent skip;
- a .bak snapshot exists before the target is replaced.
"""

import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

bootstrap_mod = importlib.import_module("04_bootstrap_kit")
l2_apply = importlib.import_module("08_l2_apply")
from test_bootstrap_kit import _db  # noqa: E402


def _kit(tmp_path: pathlib.Path) -> pathlib.Path:
    kit = tmp_path / "kit"
    bootstrap_mod.build_kit(_db(tmp_path), kit)
    return kit


def _patch(l2: pathlib.Path, target: str, cid: str, excerpt: str) -> None:
    patches = l2 / "l2_profile_patches"
    patches.mkdir(parents=True, exist_ok=True)
    (patches / f"{target}.patch.md").write_text(
        f"### {cid} [待确认] [REC-0003]\n- **原文摘录**：> {excerpt}\n",
        encoding="utf-8",
    )


def _excerpt() -> str:
    return "我的项目是芯火知识库，必须保留原文出处，不要编造没有发生的事。"


def test_missing_anchor_is_safe_stop(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    target = kit / "01-身份与当前主线.md"
    original = target.read_text(encoding="utf-8").replace("[XH-L2-PENDING-END]", "")
    target.write_text(original, encoding="utf-8")
    l2 = tmp_path / "l2"
    _patch(l2, "01-身份与当前主线.md", "L2-0001", _excerpt())

    out = tmp_path / "out"
    with pytest.raises(l2_apply.L2ApplyError) as exc:
        l2_apply.apply_unsigned(kit, l2, out)
    assert "ANCHOR_MISSING" in str(exc.value)
    # The precondition fails before evidence or profile writes.
    assert "L2-0001" not in (out / "01-身份与当前主线.md").read_text(encoding="utf-8")
    assert not (out / "_evidence" / "l2-lines.md").exists()


def test_agents_md_is_read_only(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    l2 = tmp_path / "l2"
    _patch(l2, "AGENTS.md", "L2-0001", _excerpt())
    with pytest.raises(l2_apply.L2ApplyError) as exc:
        l2_apply.apply_unsigned(kit, l2, tmp_path / "out")
    assert "AGENTS_READ_ONLY" in str(exc.value)


def test_legacy_pending_zone_is_not_duplicated(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    target = kit / "03-硬规则与表达黑话.md"
    text = target.read_text(encoding="utf-8")
    legacy = (
        "## 附：二层回流待确认区\n\n"
        "<!-- L2-BACKFILL-BEGIN · 机器生成 · 未经本人签字不生效 -->\n"
        "### L2-9000 [待确认] 旧区\n"
        "<!-- L2-BACKFILL-END -->\n\n"
    )
    target.write_text(text.replace("[XH-L2-PENDING-END]", legacy + "[XH-L2-PENDING-END]"),
                      encoding="utf-8")
    l2 = tmp_path / "l2"
    _patch(l2, "03-硬规则与表达黑话.md", "L2-0001", _excerpt())

    with pytest.raises(l2_apply.L2ApplyError) as exc:
        l2_apply.apply_unsigned(kit, l2, tmp_path / "out")
    assert "PENDING_ZONE" in str(exc.value)
    out_text = (tmp_path / "out" / "03-硬规则与表达黑话.md").read_text(encoding="utf-8")
    assert out_text.count("## 附：二层回流待确认区") == 1


def test_full_existing_zone_is_idempotent_skip(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    l2 = tmp_path / "l2"
    _patch(l2, "01-身份与当前主线.md", "L2-0001", _excerpt())
    first = tmp_path / "first"
    res1 = l2_apply.apply_unsigned(kit, l2, first)
    assert res1["applied"] == 1
    assert res1["validate_ok"], res1["validate_messages"]

    second = tmp_path / "second"
    res2 = l2_apply.apply_unsigned(first, l2, second)
    assert res2["applied"] == 0
    assert res2["skipped_existing"] == 1
    text = (second / "01-身份与当前主线.md").read_text(encoding="utf-8")
    assert text.count("## 附：二层回流待确认区") == 1
    assert text.count("L2-0001") == 1


def test_anchor_stays_last_and_backup_is_kept(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    l2 = tmp_path / "l2"
    _patch(l2, "01-身份与当前主线.md", "L2-0001", _excerpt())
    out = tmp_path / "out"
    l2_apply.apply_unsigned(kit, l2, out)
    target = out / "01-身份与当前主线.md"
    text = target.read_text(encoding="utf-8")
    assert text.rstrip().endswith("[XH-L2-PENDING-END]")
    assert "L2-0001" in text
    assert (out / "01-身份与当前主线.md.bak").is_file()