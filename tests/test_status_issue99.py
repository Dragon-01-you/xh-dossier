#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #99: `xh.py status` accepts --raw/--kit/--db/--report custom dataset
views and prints the real directory and counts; the default work/ layout stays
unchanged. Read-only display command.
"""

from __future__ import annotations

import pathlib
import sqlite3
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def run_status(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS_DIR / "xh.py"), "status", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _seed(tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("a.md", "b.json", "c.txt"):
        (raw / name).write_text("x", encoding="utf-8")

    kit = tmp_path / "mykit"
    kit.mkdir()
    for name in ("AGENTS.md", "00-总入口索引.md", "01-身份与当前主线.md",
                 "02-核心判断准则.md", "03-硬规则与表达黑话.md", "04-反面案例清单.md"):
        (kit / name).write_text("# kit", encoding="utf-8")

    db = tmp_path / "unified_index.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE records (rec_id TEXT PRIMARY KEY, role TEXT, content TEXT)")
    con.executemany("INSERT INTO records VALUES (?,?,?)",
                    [(f"REC-{i:04d}", "user", "内容") for i in range(5)])
    con.commit()
    con.close()

    report = tmp_path / "backfill_candidates.md"
    report.write_text("\n".join(["# report"] * 12), encoding="utf-8")
    return {"raw": raw, "kit": kit, "db": db, "report": report}


def test_status_custom_views_print_real_counts(tmp_path: pathlib.Path) -> None:
    paths = _seed(tmp_path)
    proc = run_status("--raw", str(paths["raw"]), "--kit", str(paths["kit"]),
                      "--db", str(paths["db"]), "--report", str(paths["report"]))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "raw-custom:" in out and "(3 files)" in out
    assert "kit-custom:" in out and "(6 files, 6 markdown)" in out
    assert "db:" in out and "(5 records" in out
    assert "report:" in out and "(12 lines" in out


def test_status_default_work_layout_kept(tmp_path: pathlib.Path) -> None:
    proc = run_status()
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for name in ("raw", "interview", "kit", "reports", "evidence"):
        assert f"{name}:" in out
    # No custom view labels when no flags are given.
    assert "raw-custom:" not in out
    assert "kit-custom:" not in out


def test_status_missing_custom_dirs_do_not_crash(tmp_path: pathlib.Path) -> None:
    proc = run_status("--raw", str(tmp_path / "nope-raw"),
                      "--kit", str(tmp_path / "nope-kit"),
                      "--db", str(tmp_path / "nope.db"),
                      "--report", str(tmp_path / "nope.md"))
    assert proc.returncode == 0, proc.stderr
    assert "(missing)" in proc.stdout
