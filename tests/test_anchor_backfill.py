#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Migration tests for `13_anchor_backfill.py` (issue #146).

Locks the behaviours promised in the ticket:
- a kit written before the anchor existed gets the anchor on every profile;
- the body is append-only (bytes before the anchor are untouched);
- a second run changes zero bytes (idempotent);
- duplicated anchors and anchors with content after them safe-stop;
- `--dry-run` reports without writing.
"""

import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

bootstrap_mod = importlib.import_module("04_bootstrap_kit")
backfill_mod = importlib.import_module("13_anchor_backfill")

from test_bootstrap_kit import _db  # noqa: E402

ANCHOR = backfill_mod.PENDING_ANCHOR


def _kit(tmp_path: pathlib.Path) -> pathlib.Path:
    kit = tmp_path / "kit"
    bootstrap_mod.build_kit(_db(tmp_path), kit)
    return kit


def _strip_anchors(kit: pathlib.Path) -> None:
    for path in sorted(kit.glob("*.md")):
        if path.name == "AGENTS.md":
            continue
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(f"\n\n{ANCHOR}\n", "\n").replace(ANCHOR + "\n", ""),
            encoding="utf-8",
        )


def test_backfill_adds_missing_anchor_and_is_idempotent(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    _strip_anchors(kit)
    before = {p.name: p.read_text(encoding="utf-8") for p in kit.glob("*.md")}

    report = backfill_mod.backfill(kit)
    assert report["changed"] == len(backfill_mod.PROFILE_FILES), report

    for name in backfill_mod.PROFILE_FILES:
        real = next(p for p in kit.glob("*.md") if p.name == name)
        text = real.read_text(encoding="utf-8")
        assert text.count(ANCHOR) == 1
        # append-only: the original body is still a prefix of the new file
        assert text.startswith(before[name].rstrip("\n"))

    # second run: zero bytes changed
    sizes = {p.name: p.stat().st_size for p in kit.glob("*.md")}
    report2 = backfill_mod.backfill(kit)
    assert report2["changed"] == 0
    assert {p.name: p.stat().st_size for p in kit.glob("*.md")} == sizes


def test_dry_run_writes_nothing(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    _strip_anchors(kit)
    sizes = {p.name: p.stat().st_size for p in kit.glob("*.md")}

    report = backfill_mod.backfill(kit, dry_run=True)
    assert report["changed"] == len(backfill_mod.PROFILE_FILES)
    assert all(row["status"] == "would_add" for row in report["files"])
    assert {p.name: p.stat().st_size for p in kit.glob("*.md")} == sizes


def test_duplicated_anchor_safe_stops(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    target = next(p for p in kit.glob("03-*.md"))
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\n" + ANCHOR + "\n",
        encoding="utf-8",
    )
    with pytest.raises(backfill_mod.AnchorBackfillError, match="ANCHOR_DUPLICATED"):
        backfill_mod.backfill(kit)


def test_content_after_anchor_safe_stops(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    target = next(p for p in kit.glob("02-*.md"))
    target.write_text(
        target.read_text(encoding="utf-8").replace(ANCHOR, ANCHOR + "\n\n后续内容\n"),
        encoding="utf-8",
    )
    with pytest.raises(backfill_mod.AnchorBackfillError, match="ANCHOR_NOT_AT_END"):
        backfill_mod.backfill(kit)
