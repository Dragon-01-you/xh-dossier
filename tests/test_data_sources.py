# -*- coding: utf-8 -*-
"""Issue #100 (Epic #74): non-whitelist carriers are counted/listed, not silently
skipped; the data-sources matrix doc stays aligned with the whitelist.
"""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

mod_clean = import_module("01_clean_and_index")


def test_non_whitelist_files_counted_not_parsed(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "note.md").write_text("## 2026-11-20 对话\nUser: 这是一句够长的真实记录需要入库\nAssistant: 已确认记下", encoding="utf-8")
    (raw / "client.db").write_bytes(b"sqlite-binary-not-parsed")
    (raw / "screenshot.png").write_bytes(b"\x89PNG\r\n")

    stats = mod_clean.clean_and_index(raw, tmp_path / "cold.db")

    # Existing contract keys stay intact.
    assert stats["indexed"] >= 1
    assert stats["total_raw"] == stats["indexed"] + stats["dedup_skipped"]
    # New accounting: two non-whitelist carriers are listed by name + extension.
    assert stats["skipped_unrecognized_files"] == 2
    names = {name for name, _ext in stats["skipped_unrecognized_detail"]}
    assert names == {"client.db", "screenshot.png"}
    exts = {ext for _name, ext in stats["skipped_unrecognized_detail"]}
    assert ".db" in exts and ".png" in exts


def test_whitelist_constant_matches_doc_matrix() -> None:
    doc = (REPO_ROOT / "docs" / "03-data-sources.md").read_text(encoding="utf-8")

    # Every whitelist extension appears in the doc.
    for ext in mod_clean.RECOGNIZED_EXTS:
        assert ext in doc, f"文档未对齐白名单扩展名 {ext}"

    # Matrix covers the five carrier classes called out in Issue #100.
    for token in ("jsonl", "sqlite", "zip", "图片", "网页登录态"):
        assert token in doc, f"矩阵缺载体类别：{token}"

    # Non-exportable / unverifiable carriers must carry an explicit marker.
    assert "不可导出" in doc
    assert "UNVERIFIED" in doc
