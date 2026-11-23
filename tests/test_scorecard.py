#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #96: decidable scorecard metrics, thresholds, and enforce-mode fail."""

import importlib
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

VALIDATOR = importlib.import_module("03_validate_kit")
BOOTSTRAP = importlib.import_module("04_bootstrap_kit")

ANSWERS_MD = """# 汇总

- 称呼：芯火
- 身份 / 阶段：学生
- 当前项目：多个 Agent 的多人对话聚合，卡在测试
- 判断准则：1A（目标与真需求优先）/ 2C（内外双验收）/ 3B（单点卡 15 分钟换路线）
- 红线：原始资料可导出但需本人批准；未经本人同意不要删文件
- 正例：先对齐需求；AI 不懂主动提问
- 反例：输出听不懂的内容；过度依赖 AI 没学到东西
"""


def _interview(tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "interview"
    folder.mkdir()
    (folder / "answers.md").write_text(ANSWERS_MD, encoding="utf-8")
    return folder


def _db(tmp_path: pathlib.Path, rows: list[tuple[str, str, str, str, str]]) -> pathlib.Path:
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                    [(a, b, c, d, e, "x", "", "stated") for a, b, c, d, e in rows])
    con.commit()
    con.close()
    return db


FULL_ROWS = [
    ("REC-0001", "a.md", "2026-11-01", "user",
     "我正在做 Agent 多人对话聚合系统，目前卡在测试环节，需要把每步产物留存下来。"),
    ("REC-0002", "a.md", "2026-11-01", "user",
     "判断原则是先对齐真实需求，再谈方法骨架，每一步都要能被本人复核。"),
    ("REC-0003", "b.md", "2026-11-02", "user",
     "有效的做法是开工前先把需求对齐，AI 不懂的地方要主动反问本人。"),
]

THIN_ROWS = [
    ("REC-0001", "a.md", "2026-11-01", "user",
     "我正在做一个网页小工具，页面上放几个按钮，能点开看详情就可以了。"),
    ("REC-0002", "a.md", "2026-11-01", "user",
     "我平时会记一些零散想法，有空的时候翻一翻，暂时没有固定的判断标准。"),
    ("REC-0003", "b.md", "2026-11-02", "user",
     "今天整理了一下收藏的链接，分类放到不同的文件夹里，方便以后查找。"),
]


def test_full_kit_scorecard_passes_thresholds(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path, FULL_ROWS)
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit, interview=_interview(tmp_path))
    card = VALIDATOR.score_kit(kit)
    assert card["overall_passed"], card["metrics"]
    metrics = card["metrics"]
    assert metrics["coverage"]["passed"]
    assert metrics["answerable_questions"]["passed"]
    assert metrics["citation_accuracy"]["value"] == 1.0
    assert metrics["mainline_unique"]["passed"]


def test_thin_kit_names_missing_slots_and_questions(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path, THIN_ROWS)
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit)
    card = VALIDATOR.score_kit(kit)
    assert not card["overall_passed"]
    assert "principle" in card["missing_slots"]
    assert "negative" in card["missing_slots"]
    assert not card["metrics"]["coverage"]["passed"]
    # The three-question answerability must state which question is unanswered.
    assert "判断准则" in card["metrics"]["answerable_questions"]["detail"]


def test_enforce_score_flips_structural_pass(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path, THIN_ROWS)
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit)
    ok_advisory, _ = VALIDATOR.validate_kit(kit, strict=False, enforce_score=False)
    ok_enforced, msgs = VALIDATOR.validate_kit(kit, strict=False, enforce_score=True)
    # Advisory leaves structural pass alone; enforced mode fails on the scorecard.
    assert not ok_enforced
    assert any("SCORECARD_FAIL" in m for m in msgs)


def test_scorecard_diagnostics_render_per_metric(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path, THIN_ROWS)
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit)
    card = VALIDATOR.score_kit(kit)
    lines = VALIDATOR.format_scorecard(card)
    assert lines[0] == "SCORECARD:"
    assert any("coverage" in ln and "FAIL" in ln for ln in lines)
    assert any("citation_accuracy" in ln for ln in lines)
