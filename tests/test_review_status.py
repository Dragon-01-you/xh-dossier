#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #90: review_status pending -> confirmed gate; verify blocks until a
human confirms. The Agent cannot self-confirm through the build path.
"""

import argparse
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

XH = importlib.import_module("xh")


def test_missing_sidecar_counts_as_pending_and_blocks(tmp_path: pathlib.Path) -> None:
    kit = tmp_path / "kit"
    kit.mkdir()
    assert XH._read_review_status(kit) == XH.REVIEW_PENDING
    blocker = XH.review_block_reason(kit)
    assert blocker is not None
    assert "pending_review" in blocker
    assert "review --confirm" in blocker


def test_corrupt_sidecar_falls_back_to_pending(tmp_path: pathlib.Path) -> None:
    kit = tmp_path / "kit"
    kit.mkdir()
    sidecar = kit / XH.REVIEW_STATUS_REL
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("{not json", encoding="utf-8")
    assert XH._read_review_status(kit) == XH.REVIEW_PENDING
    assert XH.review_block_reason(kit) is not None


def test_confirm_flips_status_and_opens_the_gate(tmp_path: pathlib.Path) -> None:
    kit = tmp_path / "kit"
    kit.mkdir()
    rc = XH.review(argparse.Namespace(kit=str(kit), confirm=True, note="本人复核通过"))
    assert rc == 0
    assert XH._read_review_status(kit) == XH.REVIEW_CONFIRMED
    assert XH.review_block_reason(kit) is None
    sidecar = (kit / XH.REVIEW_STATUS_REL).read_text(encoding="utf-8")
    assert "reviewed" in sidecar


def test_review_read_only_reports_pending_without_writing(tmp_path: pathlib.Path) -> None:
    kit = tmp_path / "kit"
    kit.mkdir()
    rc = XH.review(argparse.Namespace(kit=str(kit), confirm=False, note=None))
    assert rc == 1  # pending exits non-zero for the read-only status check
    assert not (kit / XH.REVIEW_STATUS_REL).exists()


def test_build_sidecar_starts_pending(tmp_path: pathlib.Path) -> None:
    kit = tmp_path / "kit"
    XH._write_review_status(kit, XH.REVIEW_PENDING, note="fresh build; pending personal review")
    assert XH._read_review_status(kit) == XH.REVIEW_PENDING
    # Re-confirming later must be a separate, explicit action.
    XH._write_review_status(kit, XH.REVIEW_CONFIRMED)
    assert XH._read_review_status(kit) == XH.REVIEW_CONFIRMED
