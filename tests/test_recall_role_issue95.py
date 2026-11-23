#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #95: keyword recall filters/sorts by role and the text render labels it.

Default behavior keeps both roles but lists the user's own words ahead of
assistant replies; an explicit ``role=`` argument filters to one side.
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
from importlib import import_module

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

mod01 = import_module("01_clean_and_index")
mod07 = import_module("07_recall_time_graph")

ROWS = [
    ("REC-0001", "f.md", "2026-11-01", "assistant", "好的，我们来深入拆解一下项目结构"),
    ("REC-0002", "f.md", "2026-11-02", "user", "我的项目是芯火知识库，要保留原文出处"),
    ("REC-0003", "f.md", "2026-11-03", "assistant", "我完全理解你的意思了，项目可以先跑通"),
    ("REC-0004", "f.md", "2026-11-04", "user", "我目前在做剪辑系统的项目自动化"),
]


def _db(tmp_path: pathlib.Path) -> pathlib.Path:
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT UNIQUE, event_date TEXT, date_kind TEXT)"
    )
    con.execute("CREATE VIRTUAL TABLE records_fts USING fts5(rec_id UNINDEXED, content)")
    for i, (rid, src, ts, role, content) in enumerate(ROWS):
        con.execute(
            "INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
            (rid, src, ts, role, content, f"md5-{i}", "", "stated"),
        )
        con.execute("INSERT INTO records_fts (rec_id, content) VALUES (?,?)", (rid, content))
    con.commit()
    con.close()
    return db


def test_default_sort_lists_user_records_first(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    hits = mod01.search_keyword(db, "项目")
    roles = [r["role"] for r in hits]
    assert roles == ["user", "user", "assistant", "assistant"]


def test_role_filter_keeps_only_requested_side(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    users = mod01.search_keyword(db, "项目", role="user")
    assert [r["role"] for r in users] == ["user", "user"]
    assistants = mod01.search_keyword(db, "项目", role="assistant")
    assert [r["role"] for r in assistants] == ["assistant", "assistant"]


def test_render_text_labels_role(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    report = mod07.run_recall(db, keyword="项目")
    text = mod07._render_text(report)
    assert "| user]" in text
    assert "| assistant]" in text
    # Top keyword hit must be the user's own words.
    assert report["keyword"][0]["role"] == "user"
