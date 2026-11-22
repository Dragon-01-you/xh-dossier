#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bootstrap six-file draft from a messy chat index; broad layer-2 proposal."""

import importlib
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

bootstrap_mod = importlib.import_module("04_bootstrap_kit")
backfill_mod = importlib.import_module("05_deep_backfill")


def _db(tmp_path: pathlib.Path) -> pathlib.Path:
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    rows = [
        ("REC-0001", "20261101-100000-3D可视化项目研究规划.md", "2026-11-01", "user",
         "我是个人开发者，我想做一个 3D 可视化项目，帮助计算机专业学生理解编程。"),
        ("REC-0002", "20261101-100000-3D可视化项目研究规划.md", "2026-11-01", "assistant",
         "这是一个很好的方向，可以从第一性原理开始。"),
        ("REC-0003", "20261102-100000-Obsidian知识库定制优化.md", "2026-11-02", "user",
         "我的项目是芯火知识库，必须保留原文出处，不要编造没有发生的事。"),
        ("REC-0004", "20261102-100000-Obsidian知识库定制优化.md", "2026-11-02", "user",
         "判断原则是先验证再下结论，先做最小闭环，再扩规模。"),
        ("REC-0005", "20261103-100000-剪辑系统开发.md", "2026-11-03", "user",
         "踩坑了，之前停在最后一步没上线，后来改成先跑通再优化。"),
        ("REC-0006", "20261103-100000-剪辑系统开发.md", "2026-11-03", "user",
         "这次跑通了，有效的做法是每步都给产物和退出码。"),
        ("REC-0007", "20261104-100000-技能安装.md", "2026-11-04", "user",
         "记住，禁止替本人签字，不确定的边界要标出处。"),
        ("REC-0008", "20261104-100000-技能安装.md", "2026-11-04", "user",
         "SecretId: AKIDabcdefghijklmnop 和 SecretKey: c2VjcmV0LXZhbHVl 不要写进档案。"),
        ("REC-0009", "20261105-100000-市场调研.md", "2026-11-05", "user",
         "我要做市场调研，核心是应用开发前判断真实需求。"),
        ("REC-0010", "20261105-100000-市场调研.md", "2026-11-05", "user",
         "我目前只有 PDF，偏好听而不是看，所以请生成播客稿。"),
    ]
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                    [(a, b, c, d, e, "x", "", "stated") for a, b, c, d, e in rows])
    con.commit()
    con.close()
    return db


def test_bootstrap_builds_six_valid_files_with_evidence(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    kit = tmp_path / "kit"
    res = bootstrap_mod.build_kit(db, kit)
    assert res["validate_ok"], res["validate_messages"]
    for name in bootstrap_mod.VALIDATOR.REQUIRED_KIT_FILES:
        assert bootstrap_mod.VALIDATOR.find_kit_file(kit, name) is not None
    evidence = (kit / bootstrap_mod.EVIDENCE_REL).read_text(encoding="utf-8")
    assert "REC-0001" in evidence
    # Secrets and local paths must not survive into the kit or evidence.
    joined = "\n".join(p.read_text(encoding="utf-8") for p in kit.rglob("*.md"))
    assert "AKIDabcdefghijklmnop" not in joined
    assert "c2VjcmV0LXZhbHVl" not in joined
    assert "SecretKey:" not in joined


def test_broad_layer2_finds_uncited_durable_record(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    kit = tmp_path / "kit"
    bootstrap_mod.build_kit(db, kit)
    records = backfill_mod.load_records(db)
    coverage = backfill_mod.build_coverage_index(backfill_mod.load_profiles(kit))
    proposals = backfill_mod.broad_candidates(records, coverage)
    assert proposals, "broad mode should propose at least one uncited durable record"
    assert all(p.needs_llm for p in proposals)
    assert all(p.rec_id not in coverage.covered_rec_ids for p in proposals)
