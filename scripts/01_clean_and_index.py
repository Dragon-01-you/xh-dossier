#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.1: Clean raw exported multi-platform chat logs, deduplicate by MD5, and build SQLite FTS5 cold index."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sqlite3
from typing import Any

PASTED_NOISE_RE = re.compile(r"\[Pasted text #\d+\]|^\s*[-*_]{3,}\s*$", re.MULTILINE)
MULTI_SPACE_RE = re.compile(r"\n{3,}")


def clean_text(raw: str) -> str:
    """Remove UI paste placeholders and excessive blank lines while preserving original wording."""
    text = PASTED_NOISE_RE.sub("", raw or "")
    text = MULTI_SPACE_RE.sub("\n\n", text)
    return text.strip()


def _extract_from_json(path: pathlib.Path) -> list[dict[str, str]]:
    data: Any = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    rows: list[dict[str, str]] = []

    if isinstance(data, dict):
        if "conversations" in data and isinstance(data["conversations"], list):
            items = data["conversations"]
        elif "messages" in data and isinstance(data["messages"], list):
            items = [{"title": data.get("title", path.stem), "messages": data["messages"]}]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return rows

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        ts = str(item.get("created_at") or item.get("timestamp") or item.get("date") or "unknown")
        msgs = item.get("messages")
        if isinstance(msgs, list):
            for m_idx, m in enumerate(msgs):
                if not isinstance(m, dict):
                    continue
                body = clean_text(str(m.get("content") or m.get("text") or ""))
                if len(body) < 4:
                    continue
                rows.append({
                    "source_file": path.name,
                    "created_at": str(m.get("created_at") or m.get("timestamp") or ts),
                    "role": str(m.get("role") or "user"),
                    "content": body,
                })
        else:
            body = clean_text(str(item.get("content") or item.get("text") or item.get("body") or ""))
            if len(body) >= 4:
                rows.append({
                    "source_file": path.name,
                    "created_at": ts,
                    "role": str(item.get("role") or "user"),
                    "content": body,
                })
    return rows


def _extract_from_text(path: pathlib.Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    # Split on markdown section headers (`## ` or `### `) so multi-turn logs become discrete records
    sections = re.split(r"(?m)^#{2,3}\s+", text)
    rows: list[dict[str, str]] = []
    for idx, section in enumerate(sections):
        raw_block = section.strip()
        if not raw_block:
            continue
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", raw_block)
        ts = date_m.group(1) if date_m else "unknown"
        # Drop the heading title line on sectioned markdown/txt exports
        if idx > 0 and "\n" in raw_block:
            _, raw_block = raw_block.split("\n", 1)
        body = clean_text(raw_block)
        role_m = re.match(r"^(user|assistant|ai|助手|用户)\s*[:：]\s*", body, re.IGNORECASE)
        role = "user"
        if role_m:
            lbl = role_m.group(1).lower()
            role = "assistant" if lbl in {"assistant", "ai", "助手"} else "user"
            body = body[role_m.end() :].strip()
        if len(body) < 4:
            continue
        rows.append({
            "source_file": path.name,
            "created_at": ts,
            "role": role,
            "content": body,
        })
    return rows


def clean_and_index(raw_dir: pathlib.Path, db_path: pathlib.Path) -> dict[str, int]:
    """Scan raw_dir (.json/.md/.txt), deduplicate by full-text MD5, and store into SQLite FTS5 cold DB."""
    if not raw_dir.exists():
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

        for path in sorted(raw_dir.rglob("*")):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext == ".json":
                extracted = _extract_from_json(path)
            elif ext in {".md", ".txt"}:
                extracted = _extract_from_text(path)
            else:
                continue

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

    return {"total_raw": total_raw, "dedup_skipped": dedup_skipped, "indexed": indexed}


def search_keyword(db_path: pathlib.Path, query: str, limit: int = 20) -> list[dict[str, str]]:
    """Run exact keyword search using FTS5 trigram (>=3 chars) with automatic LIKE fallback (<3 chars)."""
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
            rows = con.execute(
                """
                SELECT rec_id, source_file, created_at, role, content
                FROM records
                WHERE content LIKE ?
                LIMIT ?
                """,
                (f"%{q}%", limit),
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

    stats = clean_and_index(args.raw, args.db)
    print(f"INDEX_OK total_raw={stats['total_raw']} dedup_skipped={stats['dedup_skipped']} indexed={stats['indexed']}")
    if args.query:
        hits = search_keyword(args.db, args.query)
        print(f"QUERY '{args.query}' -> {len(hits)} hit(s)")
        for h in hits[:5]:
            print(f"  [{h['rec_id']} | {h['created_at']}] {h['content'][:90].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
