#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #93: pagination coverage reconciliation.

The extension dumps session files into raw/; this suite checks the coverage
script compares the landing count against the account list count, reports a
shortfall, and that the export guide documents the pagination protocol fields
and the unverified old-session boundary.
"""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

cov = import_module("09_export_coverage")


def _seed_raw(raw_dir: pathlib.Path, names: list[str]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (raw_dir / name).write_text("body", encoding="utf-8")


def test_coverage_ok_when_count_matches(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    _seed_raw(raw, ["会话A.md", "会话B.json", "会话C.md"])
    result, code = cov.coverage_check(raw, 3)
    assert code == 0
    assert result["ok"] is True
    assert result["missing"] == 0


def test_coverage_short_when_fewer_files_than_sessions(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    _seed_raw(raw, ["会话A.md", "会话B.md"])
    result, code = cov.coverage_check(raw, 5)
    assert code == 2
    assert result["ok"] is False
    assert result["missing"] == 3


def test_missing_raw_dir_is_error(tmp_path: pathlib.Path) -> None:
    result, code = cov.coverage_check(tmp_path / "nope", 3)
    assert code == 2
    assert result["error"] == "RAW_DIR_NOT_FOUND"


def test_manifest_lists_unmatched_titles(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    _seed_raw(raw, ["冰屋建模.md"])
    manifest = tmp_path / "titles.txt"
    manifest.write_text("冰屋建模\n人生选择哲学\n", encoding="utf-8")
    result, code = cov.coverage_check(raw, 2, manifest)
    assert code == 2
    assert "人生选择哲学" in result["unmatched_titles"]
    assert "冰屋建模" not in result["unmatched_titles"]


def test_guide_documents_pagination_protocol_and_boundary() -> None:
    guide = (REPO / "docs" / "02-multi-platform-export.md").read_text(encoding="utf-8")
    assert "has_more" in guide
    assert "cursor" in guide
    assert "UNVERIFIED" in guide
    assert "09_export_coverage.py" in guide
    assert "#93" in guide
