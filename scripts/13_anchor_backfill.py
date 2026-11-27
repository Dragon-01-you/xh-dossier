#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Idempotently restore the pending-zone end anchor in an existing six-file kit.

Older real kits were written before `04_bootstrap_kit` started appending
``[XH-L2-PENDING-END]``.  Without that anchor, `08_l2_apply` safe-stops with
``ANCHOR_MISSING`` and nothing is ever written back (applied=0).

This module is the migration path only:

- it appends the anchor to every profile that lacks it (AGENTS.md untouched);
- it never touches an anchor that is already in the right place;
- it refuses duplicated anchors and anchors with content after them;
- re-running it on a migrated kit changes zero bytes (idempotent);
- ``--dry-run`` reports what would change without writing.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pathlib
import sys

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

VALIDATOR = importlib.import_module("03_validate_kit")

PENDING_ANCHOR = "[XH-L2-PENDING-END]"
# AGENTS.md is read-only for the unsigned path, so it never carries the anchor.
PROFILE_FILES = (
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
)


class AnchorBackfillError(RuntimeError):
    """A safe-stop condition: leave the kit untouched and tell the user why."""


def _inspect(text: str) -> str:
    count = text.count(PENDING_ANCHOR)
    if count == 0:
        return "missing"
    if count > 1:
        return "duplicated"
    after = text.split(PENDING_ANCHOR, 1)[1]
    return "unchanged" if not after.strip() else "not_at_end"


def _append_anchor(text: str) -> str:
    return text.rstrip() + "\n\n" + PENDING_ANCHOR + "\n"


def _atomic_write(path: pathlib.Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def backfill(kit: pathlib.Path, *, dry_run: bool = False) -> dict:
    if not kit.is_dir():
        raise AnchorBackfillError(f"KIT_DIR_MISSING: {kit}")

    files: list[dict] = []
    changed = 0
    for canonical in PROFILE_FILES:
        real = VALIDATOR.find_kit_file(kit, canonical)
        if real is None:
            raise AnchorBackfillError(f"PROFILE_MISSING: {canonical} not found in {kit}")
        text = real.read_text(encoding="utf-8", errors="replace")
        before = len(text.encode("utf-8"))
        state = _inspect(text)
        if state == "duplicated":
            raise AnchorBackfillError(
                f"ANCHOR_DUPLICATED: {real.name} contains {text.count(PENDING_ANCHOR)} "
                f"{PENDING_ANCHOR}; keep exactly one"
            )
        if state == "not_at_end":
            raise AnchorBackfillError(
                f"ANCHOR_NOT_AT_END: {real.name} has content after {PENDING_ANCHOR}; "
                "move it to the very end by hand"
            )
        if state == "missing":
            new_text = _append_anchor(text)
            after = len(new_text.encode("utf-8"))
            if not dry_run:
                _atomic_write(real, new_text)
            changed += 1
            files.append(
                {
                    "file": real.name,
                    "status": "would_add" if dry_run else "added",
                    "bytes_before": before,
                    "bytes_after": after,
                    "delta": after - before,
                }
            )
        else:
            files.append(
                {
                    "file": real.name,
                    "status": "unchanged",
                    "bytes_before": before,
                    "bytes_after": before,
                    "delta": 0,
                }
            )

    return {
        "kit": str(kit),
        "dry_run": dry_run,
        "changed": changed,
        "files": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Idempotently add the pending-zone end anchor to an existing kit."
    )
    ap.add_argument("--kit", required=True, type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args()

    try:
        report = backfill(args.kit, dry_run=args.dry_run)
    except AnchorBackfillError as exc:
        print(f"ANCHOR_BACKFILL_ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["files"]:
            print(
                f"{row['file']}: {row['status']} "
                f"({row['bytes_before']} -> {row['bytes_after']} bytes)"
            )
    print(
        f"ANCHOR_BACKFILL changed={report['changed']} "
        f"total={len(report['files'])} dry_run={report['dry_run']} kit={report['kit']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
