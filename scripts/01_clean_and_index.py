#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.1: Clean raw exported multi-platform chat logs (.json/.jsonl/.md/.txt), deduplicate by MD5, and build SQLite FTS5 cold index."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sqlite3
import zipfile
from typing import Any

PASTED_NOISE_RE = re.compile(r"\[Pasted text #\d+\]|^\s*[-*_]{3,}\s*$", re.MULTILINE)
MULTI_SPACE_RE = re.compile(r"\n{3,}")

# Role headings used by common exporters:
#   AfterChat:            ### 🧑‍💻 User / ### 🤖 Assistant
#   ScriptCat exporter:   ## 🧑 User     / ## 🤖 DeepSeek AI
ROLE_HEADING_RE = re.compile(
    r"(?m)^#{2,4}[ \t]*(?P<label>(?:🧑‍💻|🧑|👤|🤖|👩‍💻|👨‍💻)[^\n]{0,40})[ \t]*$"
)
TEXT_EXTS = {".md", ".txt", ".json", ".jsonl"}


def read_text_detected(path: pathlib.Path) -> str:
    """Decode a text export using BOM/UTF-8/UTF-16/GB18030, never silently replacing bytes."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # UTF-16 without BOM: many NUL bytes in ASCII-heavy text.
    if raw.count(b"\x00") > max(2, len(raw) // 10):
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    # GB18030 covers GBK/GB2312; raises UnicodeDecodeError on truly invalid bytes.
    return raw.decode("gb18030")


def _parse_export_time(text: str) -> str:
    """Extract a date from AfterChat `**Time:**` or ScriptCat `**Date**: M/D/YYYY` metadata."""
    m = re.search(r"\*\*Time:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    m = re.search(r"\*\*Date\*\*:\s*(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        first, second, year = (int(g) for g in m.groups())
        month, day = (first, second) if first <= 12 else (second, first)
        return f"{year:04d}-{month:02d}-{day:02d}"
    return "unknown"


def _strip_wrapping_code_fence(body: str) -> str:
    """Drop separator rules and a single ```lang ... ``` wrapper that some exporters add around message text."""
    lines = body.strip().splitlines()
    while lines and lines[0].strip() in {"", "---", "***", "___"}:
        lines.pop(0)
    while lines and lines[-1].strip() in {"", "---", "***", "___"}:
        lines.pop()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return "\n".join(lines).strip()


def _role_from_label(label: str) -> str | None:
    lowered = label.lower()
    if "🤖" in label:
        return "assistant"
    if any(mark in label for mark in ("🧑", "👤", "👩", "👨")):
        return "user"
    if "assistant" in lowered or re.search(r"\bai\b", lowered):
        return "assistant"
    if "user" in lowered or "用户" in label:
        return "user"
    return None


def _extract_role_heading_rows(text: str, source_name: str) -> list[dict[str, str]]:
    """Parse conversations split by emoji role headings; ignores title/URL preamble."""
    matches = list(ROLE_HEADING_RE.finditer(text))
    if not matches:
        return []
    file_ts = _parse_export_time(text)
    rows: list[dict[str, str]] = []
    for idx, match in enumerate(matches):
        role = _role_from_label(match.group("label"))
        if role is None:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = _strip_wrapping_code_fence(text[start:end])
        body = clean_text(body)
        if len(body) < 4:
            continue
        rows.append({
            "source_file": source_name,
            "created_at": file_ts,
            "role": role,
            "content": body,
        })
    return rows


def clean_text(raw: str) -> str:
    """Remove UI paste placeholders and excessive blank lines while preserving original wording."""
    text = PASTED_NOISE_RE.sub("", raw or "")
    text = MULTI_SPACE_RE.sub("\n\n", text)
    return text.strip()


def _flatten_content(val: Any) -> str:
    """Safely normalize string, parts list, or content dicts into plain text without repr(dict) clutter."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        parts = [_flatten_content(item) for item in val]
        return "\n".join(p for p in parts if p)
    if isinstance(val, dict):
        if "parts" in val:
            return _flatten_content(val["parts"])
        for key in ("text", "content", "value", "body"):
            if key in val:
                return _flatten_content(val[key])
        return ""
    return str(val)


def _records_from_json_obj(data: Any, source_name: str) -> list[dict[str, str]]:
    """Extract normalized records from ChatGPT mapping exports, conversation lists, or flat message objects."""
    rows: list[dict[str, str]] = []

    if isinstance(data, dict):
        if "conversations" in data and isinstance(data["conversations"], list):
            items: list[Any] = data["conversations"]
        elif "messages" in data and isinstance(data["messages"], list):
            items = [{"created_at": data.get("created_at") or data.get("timestamp"), "messages": data["messages"]}]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return rows

    for item in items:
        if not isinstance(item, dict):
            continue
        ts = str(item.get("created_at") or item.get("timestamp") or item.get("create_time") or item.get("date") or item.get("time") or "unknown")

        # Handle ChatGPT official `mapping` node tree format
        if isinstance(item.get("mapping"), dict):
            for node in item["mapping"].values():
                if not isinstance(node, dict):
                    continue
                msg = node.get("message")
                if not isinstance(msg, dict):
                    continue
                author = msg.get("author") if isinstance(msg.get("author"), dict) else {}
                role = str(author.get("role") or msg.get("role") or "user")
                if role == "system":
                    continue
                body = clean_text(_flatten_content(msg.get("content")))
                if len(body) >= 4:
                    rows.append({
                        "source_file": source_name,
                        "created_at": str(msg.get("create_time") or ts),
                        "role": role,
                        "content": body,
                    })
            continue

        msgs = item.get("messages")
        if isinstance(msgs, list):
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                body = clean_text(_flatten_content(m.get("content") if "content" in m else m.get("text")))
                if len(body) >= 4:
                    rows.append({
                        "source_file": source_name,
                        "created_at": str(m.get("created_at") or m.get("timestamp") or m.get("time") or ts),
                        "role": str(m.get("role") or "user"),
                        "content": body,
                    })
        else:
            raw_body = item.get("content") if "content" in item else (item.get("text") if "text" in item else item.get("body"))
            body = clean_text(_flatten_content(raw_body))
            if len(body) >= 4:
                rows.append({
                    "source_file": source_name,
                    "created_at": ts,
                    "role": str(item.get("role") or "user"),
                    "content": body,
                })
    return rows


def _extract_from_json(path: pathlib.Path, text: str | None = None) -> list[dict[str, str]]:
    text = (text if text is not None else read_text_detected(path)).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"WARN: skipped malformed JSON {path.name}: {exc}")
        return []
    return _records_from_json_obj(data, path.name)


def _extract_from_jsonl(path: pathlib.Path, text: str | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    content = text if text is not None else read_text_detected(path)
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"WARN: skipped malformed JSONL line {path.name}:{line_no}: {exc}")
            continue
        rows.extend(_records_from_json_obj(obj, path.name))
    return rows


def _extract_from_text(path: pathlib.Path, text: str | None = None) -> list[dict[str, str]]:
    text = text if text is not None else read_text_detected(path)

    # Emoji role headings cover AfterChat and ScriptCat-style exporters.
    role_rows = _extract_role_heading_rows(text, path.name)
    if role_rows:
        return role_rows

    file_ts = "unknown"
    ts_m = re.search(r"\*\*Time:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    if ts_m:
        file_ts = ts_m.group(1)

    sections = re.split(r"(?m)^#{2,3}\s+", text)
    rows = []
    turn_re = re.compile(r"(?mi)^(?=(?:user|assistant|ai|助手|用户)\s*[:：])")

    for idx, section in enumerate(sections):
        raw_block = section.strip()
        if not raw_block:
            continue
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", raw_block)
        ts = date_m.group(1) if date_m else file_ts
        if idx > 0:
            # Skip heading-only sections with no body lines beneath them
            if "\n" not in raw_block:
                continue
            _, raw_block = raw_block.split("\n", 1)

        turns = [t.strip() for t in turn_re.split(raw_block) if t.strip()]
        for turn in turns:
            body = clean_text(turn)
            role_m = re.match(r"^(user|assistant|ai|助手|用户)\s*[:：]\s*", body, re.IGNORECASE)
            role = "user"
            if role_m:
                lbl = role_m.group(1).lower()
                role = "assistant" if lbl in {"assistant", "ai", "助手"} else "user"
                body = body[role_m.end() :].strip()
            if len(body) >= 4:
                rows.append({
                    "source_file": path.name,
                    "created_at": ts,
                    "role": role,
                    "content": body,
                })
    return rows


def _safe_extract_zip(src: pathlib.Path, dest: pathlib.Path) -> int:
    """Extract only text exports from a zip, rejecting absolute/traversal paths. Returns file count."""
    extracted = 0
    with zipfile.ZipFile(src) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = pathlib.PurePosixPath(info.filename).parts
            if info.filename.startswith("/") or ".." in parts:
                continue
            target = dest.joinpath(*parts)
            if target.suffix.lower() not in TEXT_EXTS:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as rf, open(target, "wb") as wf:
                wf.write(rf.read())
            extracted += 1
    return extracted


def clean_and_index(raw_dir: pathlib.Path, db_path: pathlib.Path) -> dict[str, object]:
    """Scan raw_dir (.json/.jsonl/.md/.txt, plus .zip archives), deduplicate by full-text MD5, and store into SQLite FTS5 cold DB."""
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Raw directory not found: {raw_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE records (
                rec_id TEXT PRIMARY KEY,
                source_file TEXT NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                md5 TEXT NOT NULL UNIQUE
            )
            """
        )
        con.execute("CREATE VIRTUAL TABLE records_fts USING fts5(rec_id UNINDEXED, content, tokenize='trigram')")

        seen_md5: set[str] = set()
        total_raw = 0
        dedup_skipped = 0
        indexed = 0
        decode_failed = 0
        decode_failed_files: list[str] = []
        zip_extracted = 0

        # "Export all" usually produces a zip; unzip first so users need no manual step.
        search_dirs = [raw_dir]
        for zpath in sorted(raw_dir.rglob("*.zip")):
            dest = db_path.parent / "_unzipped" / zpath.stem
            try:
                n = _safe_extract_zip(zpath, dest)
            except (zipfile.BadZipFile, OSError) as exc:
                print(f"WARN: skipped zip {zpath.name}: {exc}")
                continue
            if n:
                zip_extracted += n
                search_dirs.append(dest)

        paths: list[pathlib.Path] = []
        for folder in search_dirs:
            paths.extend(sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTS))

        for path in paths:
            try:
                text = read_text_detected(path)
            except (UnicodeDecodeError, OSError) as exc:
                decode_failed += 1
                decode_failed_files.append(path.name)
                print(f"WARN: skipped undecodable file {path.name}: {exc}")
                continue

            ext = path.suffix.lower()
            if ext == ".json":
                extracted = _extract_from_json(path, text)
            elif ext == ".jsonl":
                extracted = _extract_from_jsonl(path, text)
            else:
                extracted = _extract_from_text(path, text)

            for item in extracted:
                total_raw += 1
                digest = hashlib.md5(item["content"].encode("utf-8")).hexdigest()
                if digest in seen_md5:
                    dedup_skipped += 1
                    continue
                seen_md5.add(digest)
                indexed += 1
                rec_id = f"REC-{indexed:04d}"
                con.execute(
                    "INSERT INTO records (rec_id, source_file, created_at, role, content, md5) VALUES (?, ?, ?, ?, ?, ?)",
                    (rec_id, item["source_file"], item["created_at"], item["role"], item["content"], digest),
                )
                con.execute("INSERT INTO records_fts (rec_id, content) VALUES (?, ?)", (rec_id, item["content"]))

        con.commit()
    finally:
        con.close()

    return {
        "total_raw": total_raw,
        "dedup_skipped": dedup_skipped,
        "indexed": indexed,
        "decode_failed": decode_failed,
        "decode_failed_files": decode_failed_files,
        "zip_extracted": zip_extracted,
    }


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_keyword(db_path: pathlib.Path, query: str, limit: int = 20) -> list[dict[str, str]]:
    """Run exact keyword search using FTS5 trigram (>=3 chars) with escaped SQL LIKE fallback (<3 chars)."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    q = query.strip()
    if not q:
        return []

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        if len(q) >= 3:
            safe_q = '"' + q.replace('"', '""') + '"'
            rows = con.execute(
                """
                SELECT r.rec_id, r.source_file, r.created_at, r.role, r.content
                FROM records_fts f
                JOIN records r ON r.rec_id = f.rec_id
                WHERE records_fts MATCH ?
                LIMIT ?
                """,
                (safe_q, limit),
            ).fetchall()
        else:
            escaped = _escape_like(q)
            rows = con.execute(
                """
                SELECT rec_id, source_file, created_at, role, content
                FROM records
                WHERE content LIKE ? ESCAPE '\\'
                LIMIT ?
                """,
                (f"%{escaped}%", limit),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean raw chat exports and build FTS5 cold archive.")
    parser.add_argument("--raw", required=True, type=pathlib.Path, help="Read-only raw export directory")
    parser.add_argument("--db", required=True, type=pathlib.Path, help="Output SQLite DB path")
    parser.add_argument("--query", default="", help="Optional test keyword query after indexing")
    args = parser.parse_args()

    # A naive first run often has an empty or mistyped raw/ folder. A traceback
    # (or a green "INDEX_OK indexed=0") is indistinguishable from success and
    # sends the user into an empty four-way report. Fail loudly with the next
    # action instead.
    if not args.raw.is_dir():
        print(f"RAW_DIR_NOT_FOUND: {args.raw}")
        print("请先完成 Stage 2：把导出的 .md/.json/.jsonl/.txt 放进 raw/ 目录（参考 docs/02-multi-platform-export.md）。")
        return 2

    stats = clean_and_index(args.raw, args.db)
    if stats["decode_failed"]:
        print(
            f"WARN_DECODE_FAILED: {stats['decode_failed']} 个文件无法解码，已跳过："
            + ", ".join(stats["decode_failed_files"][:5])
        )
    if stats["indexed"] == 0:
        print(
            f"INDEX_EMPTY: 未在 {args.raw} 找到可索引的 .json/.jsonl/.md/.txt 记录"
            f"（total_raw={stats['total_raw']}, decode_failed={stats['decode_failed']}, "
            f"zip_extracted={stats['zip_extracted']}）。"
        )
        print("不要把 indexed=0 当成成功；请检查导出文件是否真的落地，或先运行 scripts/00_export_wizard.py。")
        return 2
    print(
        f"INDEX_OK total_raw={stats['total_raw']} dedup_skipped={stats['dedup_skipped']} "
        f"indexed={stats['indexed']} decode_failed={stats['decode_failed']} "
        f"zip_extracted={stats['zip_extracted']}"
    )
    if args.query:
        hits = search_keyword(args.db, args.query)
        print(f"QUERY '{args.query}' -> {len(hits)} hit(s)")
        for h in hits[:5]:
            print(f"  [{h['rec_id']} | {h['created_at']}] {h['content'][:90].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
