#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #10 integration: verify 01 stores T and T' as separate columns."""

import pathlib
import sqlite3
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import importlib

mod_clean = importlib.import_module("01_clean_and_index")
from event_time import UNVERIFIED  # noqa: E402


def _make_raw(tmp_path: pathlib.Path) -> pathlib.Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "turns.md").write_text(
        "## 2026-11-22 回忆\n"
        "User: 大一那会我做过一个校园卡项目\n"
        "Assistant: 这确实是很早以前的事\n"
        "User: 今天我先定了验收标准\n"
        "Assistant: 今天这份验收标准已经写清楚\n"
        "User: 记得 2025-09-20 我砍掉了闲鱼副业\n"
        "Assistant: 那次确实停掉了\n"
        "User: 记得 2025-02-30 那版，后来改了\n"
        "Assistant: 这个日期需要核对\n",
        encoding="utf-8",
    )
    return raw


def test_event_date_and_date_kind_are_persisted(tmp_path: pathlib.Path) -> None:
    raw = _make_raw(tmp_path)
    db = tmp_path / "event.db"
    stats = mod_clean.clean_and_index(raw, db)
    assert stats["indexed"] == 8

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    try:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(records)")}
        assert {"created_at", "event_date", "date_kind"} <= columns
        rows = [dict(row) for row in con.execute("SELECT * FROM records ORDER BY rec_id")]
    finally:
        con.close()

    retro = [r for r in rows if r["content"] == "大一那会我做过一个校园卡项目"][0]
    assert retro["created_at"] == "2026-11-22"
    assert retro["event_date"] == UNVERIFIED
    assert retro["date_kind"] == "retrospective"

    now = [r for r in rows if r["content"] == "今天我先定了验收标准"][0]
    assert now["created_at"] == "2026-11-22"
    assert now["event_date"] == "2026-11-22"
    assert now["date_kind"] == "stated"

    # Assistant prose must not be treated as the user's memory, even when it
    # contains retrospective words like "以前". It gets no event date at all.
    assistant = [r for r in rows if r["content"].startswith("这确实是很早以前")][0]
    assert assistant["event_date"] == ""
    assert assistant["date_kind"] == "unknown"

    anchored = [r for r in rows if r["content"] == "记得 2025-09-20 我砍掉了闲鱼副业"][0]
    assert anchored["created_at"] == "2026-11-22"
    assert anchored["event_date"] == "2025-09-20"
    assert anchored["date_kind"] == "retrospective"

    invalid = [r for r in rows if r["content"].startswith("记得 2025-02-30")][0]
    assert invalid["event_date"] == UNVERIFIED
    assert invalid["date_kind"] == "retrospective"


def test_old_database_without_event_columns_is_not_rewritten(tmp_path: pathlib.Path) -> None:
    """01 recreates the DB from raw; an old DB is replaced, not silently mutated."""
    raw = _make_raw(tmp_path)
    db = tmp_path / "old.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, role TEXT, content TEXT, md5 TEXT)"
    )
    con.commit()
    con.close()

    stats = mod_clean.clean_and_index(raw, db)
    assert stats["indexed"] == 8
    con = sqlite3.connect(str(db))
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(records)")}
    finally:
        con.close()
    assert {"event_date", "date_kind"} <= columns
