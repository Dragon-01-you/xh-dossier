#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke test for the EXPERIMENTAL layer-2 backfill prototype (Issue #6).

This asserts only that the script RUNS and emits a structured report. It does
NOT assert detection quality — false positives are a documented known limit.
"""

import importlib.util
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("second_pass", SCRIPTS / "04_second_pass_backfill.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def test_second_pass_runs_and_returns_structure(tmp_path):
    import sqlite3

    db = tmp_path / "mini.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE records (rec_id TEXT, source_file TEXT, created_at TEXT, role TEXT, content TEXT, md5 TEXT)"
    )
    con.execute(
        "INSERT INTO records VALUES ('REC-0001','a.md','2026-01-01','user','上周那个事我一直没发出去','x')"
    )
    con.commit()
    con.close()

    report = sp.run_second_pass(db, None)
    assert "total_records" in report and report["total_records"] == 1
    assert "repeat_complaints_or_mistakes" in report
    assert "untold_candidates" in report
    assert "repeated_phrases" in report


def test_report_markdown_has_sections():
    md = sp.render_report({
        "total_records": 1,
        "user_records": 1,
        "first_pass_claimed": 0,
        "repeat_complaints_or_mistakes": [],
        "untold_candidates": [],
        "repeated_phrases": [],
    })
    assert "二层回流候选" in md
    assert "深度回流建议" in md
