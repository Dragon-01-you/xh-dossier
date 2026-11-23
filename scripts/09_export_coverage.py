#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 2.5: reconcile exported raw files against the session list count (#93).

The browser extension dumps one or more files per session into ``raw/``. This
script checks the exported raw count against the session count the account
list actually shows, so a truncated / partial pagination run cannot pass off
as a full archive.

Pagination itself runs inside the third-party extension against the live site;
this script only verifies the landing result. Protocol fields (``has_more``,
``cursor`` / ``page_token``) are documented in ``docs/02-multi-platform-export.md``
§0.5 and must be re-confirmed against the real site before being treated as
stable.

Usage::

    python scripts/09_export_coverage.py --raw work/raw --expected 331
    python scripts/09_export_coverage.py --raw work/raw --expected 331 --list manifest.txt

Exit codes: 0 coverage matched, 2 shortfall / bad input.
"""

from __future__ import annotations

import argparse
import pathlib

RAW_SUFFIXES = {".md", ".json", ".jsonl", ".txt"}


def count_raw(raw_dir: pathlib.Path) -> tuple[int | None, list[pathlib.Path]]:
    """Return (file count, files). Count is None when the directory is missing."""
    if not raw_dir.is_dir():
        return None, []
    files = [
        p for p in sorted(raw_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in RAW_SUFFIXES
    ]
    return len(files), files


def _load_manifest(manifest: pathlib.Path | None) -> list[str]:
    if manifest is None or not manifest.is_file():
        return []
    return [
        line.strip(" #-*\t")
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]


def coverage_check(
    raw_dir: pathlib.Path,
    expected: int,
    manifest: pathlib.Path | None = None,
) -> tuple[dict[str, object], int]:
    """Compare raw landing files against ``expected`` session count.

    A session may split into several files, so the check is conservative:
    ``raw_files >= expected`` passes. When a manifest (one title per line) is
    given, titles not represented in any raw file name are listed as unmatched.
    """
    count, files = count_raw(raw_dir)
    result: dict[str, object] = {
        "raw_dir": str(raw_dir),
        "raw_files": count,
        "expected": expected,
    }
    if count is None:
        result["error"] = "RAW_DIR_NOT_FOUND"
        return result, 2
    if expected < 0:
        result["error"] = "EXPECTED_NEGATIVE"
        return result, 2

    result["missing"] = max(0, expected - count)
    unmatched: list[str] = []
    titles = _load_manifest(manifest)
    if titles:
        haystack = " ".join(p.stem for p in files)
        unmatched = [title for title in titles if title and title not in haystack]
    result["unmatched_titles"] = unmatched
    result["ok"] = count >= expected and not unmatched
    return result, (0 if result["ok"] else 2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile exported raw files against the session list count.")
    ap.add_argument("--raw", required=True, type=pathlib.Path, help="Raw export directory")
    ap.add_argument("--expected", type=int, required=True,
                    help="Session count shown in the account conversation list")
    ap.add_argument("--list", dest="manifest", type=pathlib.Path, default=None,
                    help="Optional manifest: one session title per line")
    args = ap.parse_args()

    result, code = coverage_check(args.raw, args.expected, args.manifest)
    if result.get("error") == "RAW_DIR_NOT_FOUND":
        print(f"RAW_DIR_NOT_FOUND: {args.raw}")
        print("先完成 Stage 2 导出（参考 docs/02-multi-platform-export.md），再核对覆盖数。")
        return 2
    if result.get("error") == "EXPECTED_NEGATIVE":
        print("EXPECTED_NEGATIVE: --expected 不能为负数")
        return 2

    raw_files = result["raw_files"]
    expected = result["expected"]
    if code == 0:
        print(f"COVERAGE_OK raw={raw_files} expected={expected}")
    else:
        print(f"COVERAGE_SHORT raw={raw_files} expected={expected} missing={result['missing']}")
    unmatched = result.get("unmatched_titles") or []
    if unmatched:
        print("UNMATCHED_TITLES:")
        for title in unmatched:
            print(f"  - {title}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
