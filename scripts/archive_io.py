#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Archive extraction and garbled-filename diagnosis (issue #55).

Background
----------
Release zips built by Python :mod:`zipfile` set the EFS UTF-8 flag (bit 0x800)
on non-ASCII entry names, and the stored bytes are valid UTF-8. Info-ZIP
UnZip 6.00 (2009) ignores that flag and decodes names with the local charset,
so Chinese filenames come out as mojibake (``цА╗...`` / ``µÇ╗...`` / raw
surrogate bytes, depending on locale). Re-packing with the flag set does NOT
help: the flag was already there.

Extraction main paths here use the Python standard library (:mod:`zipfile` /
:mod:`tarfile`), which honour UTF-8 names. External unzip/bsdtar are only
last-resort fallbacks, and the doctor tells the user apart from a truly
missing file.

This module is stdlib-only on purpose: it runs before any third-party dep is
installed.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys
import tarfile
import zipfile

# --- garbled-name detection -------------------------------------------------

GARBLED_MARKERS = ("锟斤拷", "ï¿½", "\ufffd")

# Latin-1 / CP437 characters that frequently show up in 8-bit decode mojibake.
_CP437_MOJIBAKE_CHARS = set(
    "µ¢£¥§¬°±·ªº¿ÑñÓóÚúÝýÞþÐÆæØø¤Çç"
)


def _has_surrogate(name: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in name)


def _has_cjk(name: str) -> bool:
    return any(0x4E00 <= ord(ch) <= 0x9FFF for ch in name)


def _suspicious_char_count(name: str) -> int:
    count = 0
    for ch in name:
        o = ord(ch)
        if (
            0x0400 <= o <= 0x04FF  # Cyrillic (ц Ш ч ...)
            or 0x0370 <= o <= 0x03FF  # Greek (Φ σ µ ...)
            or 0x2500 <= o <= 0x257F  # box drawing (╗ ┐ ┌ ─ ...)
            or 0x2190 <= o <= 0x21FF  # arrows
            or ch in _CP437_MOJIBAKE_CHARS
        ):
            count += 1
    return count


def _reversible_mojibake(name: str) -> bool:
    """True if the name decodes back to readable CJK via a classic bad charset.

    Covers the two common round trips:
    - UTF-8 bytes decoded as GBK  -> ``鏍稿績...``
    - UTF-8 bytes decoded as CP437/CP866 -> ``µÇ╗...`` / ``цА╗...``
    """
    for enc in ("gbk", "cp437", "cp866"):
        try:
            recovered = name.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if _has_cjk(recovered):
            return True
    return False


def display_name(name: str) -> str:
    """Make a filename safe to print/JSON-encode.

    On Linux a name with invalid bytes comes back through ``surrogateescape``;
    lone surrogates cannot be encoded to UTF-8 and would crash ``json.dumps``.
    Undecodable bytes become U+FFFD instead.
    """
    return name.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


def is_garbled_name(name: str) -> bool:
    """Heuristic: does this filename look like charset-corrupted text?"""
    if not name:
        return False
    if _has_surrogate(name) or any(marker in name for marker in GARBLED_MARKERS):
        return True
    if _has_cjk(name):
        # GBK double-decode keeps rare CJK glyphs; only reversible ones count.
        return _reversible_mojibake(name)
    return _suspicious_char_count(name) >= 2 or _reversible_mojibake(name)


# --- missing-vs-mojibake diagnosis -----------------------------------------


@dataclasses.dataclass
class MissingDiagnosis:
    """Result of checking required files against a possibly-garbled checkout."""

    #: required relpaths that are absent under their canonical name
    missing: list[str]
    #: canonical relpath -> actual garbled relpath found on disk
    garbled: dict[str, str]


def diagnose_missing(root: pathlib.Path, required: list[str]) -> MissingDiagnosis:
    """Split ``required`` into truly missing files and mojibake-renamed ones.

    A garbled entry is matched to its canonical file by the leading two-digit
    index (``00-`` ...) and the suffix, which survive 8-bit decoding because
    ASCII bytes pass through untouched.
    """
    missing: list[str] = []
    garbled: dict[str, str] = {}

    for rel in required:
        rel_path = pathlib.PurePosixPath(rel)
        if (root / rel).is_file():
            continue
        missing.append(rel)

        parent = root / rel_path.parent
        if not parent.is_dir():
            continue
        expected_base = rel_path.name
        prefix = expected_base[:2]
        suffix = rel_path.suffix
        for child in sorted(parent.iterdir()):
            if not child.is_file():
                continue
            if (
                child.name[:2] == prefix
                and child.suffix == suffix
                and is_garbled_name(child.name)
            ):
                garbled[rel] = child.relative_to(root).as_posix()
                break

    return MissingDiagnosis(missing=missing, garbled=garbled)


def encoding_error_message(diag: MissingDiagnosis) -> str:
    """Human-readable advice for the mojibake case (issue #55)."""
    lines = [
        "文件名编码损坏（文件其实在，不是缺模板）：",
    ]
    for expected, actual in diag.garbled.items():
        lines.append(f"  {display_name(actual)}  ← 应为 {expected}")
    lines += [
        "原因：Info-ZIP unzip 6.00 等老解压器忽略 zip 内的 UTF-8 文件名标志，"
        "按本地代码页解释文件名；重新打包、再打一次 UTF-8 标志也修不好。",
        "请改用下面任一方式重新解压（不要用 unzip 6.00 直接解含中文文件名的 zip）：",
        "  Linux：  python3 -m zipfile -e 发布包.zip 目标目录",
        "          或下载 .tar.gz 包后：tar -xzf 发布包.tar.gz -C 目标目录",
        "  Windows：资源管理器右键“全部解压”，或 python -m zipfile -e 发布包.zip 目标目录",
    ]
    return "\n".join(lines)


# --- stdlib extraction main paths -------------------------------------------


def extract_zip(archive: pathlib.Path, dest: pathlib.Path) -> None:
    """Extract a zip with :mod:`zipfile`, which honours the UTF-8 EFS flag."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)


def extract_tar(archive: pathlib.Path, dest: pathlib.Path) -> None:
    """Extract a tar/.tar.gz with stdlib :mod:`tarfile`."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tf:
        try:
            tf.extractall(dest, filter="data")
        except TypeError:
            # Python < 3.12 has no ``filter`` kwarg.
            tf.extractall(dest)


def extract_archive(archive: pathlib.Path, dest: pathlib.Path) -> str:
    """Dispatch by suffix; returns the backend actually used.

    Main path is always the Python stdlib. External tools (unzip/bsdtar) are
    deliberately not called here: they are the last-resort fallbacks wired into
    the platform install scripts, with a loud warning when chosen.
    """
    name = archive.name.lower()
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        extract_tar(archive, dest)
        return "tarfile"
    if name.endswith(".zip"):
        extract_zip(archive, dest)
        return "zipfile"
    raise ValueError(f"不支持的压缩包格式：{archive.name}（仅支持 .zip / .tar.gz / .tgz）")


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="XH-Dossier archive extractor (stdlib, UTF-8 safe).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="extract an archive into a directory")
    p_extract.add_argument("archive")
    p_extract.add_argument("dest")

    p_list = sub.add_parser("list", help="list entry names (repr, to spot mojibake)")
    p_list.add_argument("archive")

    args = parser.parse_args(argv)

    if args.command == "extract":
        backend = extract_archive(pathlib.Path(args.archive), pathlib.Path(args.dest))
        print(f"EXTRACT_OK backend={backend} archive={args.archive} dest={args.dest}")
        return 0

    archive = pathlib.Path(args.archive)
    if archive.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(archive, "r:*") as tf:
            for member in tf.getnames():
                print(repr(member))
    else:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                print(repr(info.filename))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
