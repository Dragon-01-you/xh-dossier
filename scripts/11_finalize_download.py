#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Finalize browser .crdownload files without re-exporting.

Edge can write all bytes and then crash during the rename handshake
(state=4 INTERRUPTED, interrupt_reason=50 CRASH). This helper waits for a
stable size, copies the .crdownload to its proper .md name, and verifies byte
count. It never deletes the original.

This is a recovery step, not a claim that the browser itself is fixed.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import time


def stable_size(path: pathlib.Path, wait_seconds: int) -> bool:
    if wait_seconds <= 0:
        return True
    try:
        first = path.stat().st_size
    except OSError:
        return False
    time.sleep(wait_seconds)
    try:
        second = path.stat().st_size
    except OSError:
        return False
    return first == second and second > 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy .crdownload to .md after size stabilizes.")
    parser.add_argument("--source-dir", type=pathlib.Path, required=True,
                        help="browser download directory containing .crdownload")
    parser.add_argument("--target-dir", type=pathlib.Path, default=None,
                        help="where to write .md (default: same directory)")
    parser.add_argument("--stable-seconds", type=int, default=3,
                        help="wait this long and require unchanged size")
    parser.add_argument("--only", default=None,
                        help="only process a filename substring")
    args = parser.parse_args()

    source_dir = args.source_dir.expanduser().resolve()
    target_dir = (args.target_dir.expanduser().resolve() if args.target_dir else source_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    partials = sorted(source_dir.rglob("*.crdownload"))
    if args.only:
        partials = [p for p in partials if args.only in p.name]
    if not partials:
        print("FINALIZE_NONE: 没有 .crdownload")
        return 1

    ok = 0
    for path in partials:
        final_name = path.name[:-len(".crdownload")]
        target = target_dir / final_name
        if not stable_size(path, args.stable_seconds):
            print(f"DOWNLOAD_UNSTABLE: {path}")
            continue
        try:
            shutil.copy2(path, target)
            if target.stat().st_size != path.stat().st_size:
                print(f"DOWNLOAD_SIZE_MISMATCH: {path} -> {target}")
                continue
            print(f"DOWNLOAD_FINALIZED: {target} ({target.stat().st_size} bytes)")
            ok += 1
        except OSError as exc:
            print(f"DOWNLOAD_LOCKED: {path} ({exc})")
    print(f"FINALIZE_OK finalized={ok}/{len(partials)}")
    return 0 if ok == len(partials) else 1


if __name__ == "__main__":
    raise SystemExit(main())
