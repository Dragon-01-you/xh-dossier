#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #98: blind package copies only the six files; scoring returns PASS/FAIL
per question, with no raw/interview context leaked into the package."""

import argparse
import importlib
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

BLIND = importlib.import_module("blind_test")
BOOTSTRAP = importlib.import_module("04_bootstrap_kit")
XH = importlib.import_module("xh")

ANSWERS_MD = """# 汇总

- 称呼：芯火
- 身份 / 阶段：学生
- 当前项目：多个 Agent 的多人对话聚合，卡在测试
- 判断准则：1A（目标与真需求优先）/ 2C（内外双验收）/ 3B（单点卡 15 分钟换路线）
- 红线：原始资料可导出但需本人批准；未经本人同意不要删文件
- 正例：先对齐需求；AI 不懂主动提问
- 反例：输出听不懂的内容；过度依赖 AI 没学到东西
"""

ROWS = [
    ("REC-0001", "a.md", "2026-11-01", "user",
     "我正在做 Agent 多人对话聚合系统，目前卡在测试环节，需要把每步产物留存下来。"),
    ("REC-0002", "a.md", "2026-11-01", "user",
     "判断原则是先对齐真实需求，再谈方法骨架，每一步都要能被本人复核。"),
    ("REC-0003", "b.md", "2026-11-02", "user",
     "有效的做法是开工前先把需求对齐，AI 不懂的地方要主动反问本人。"),
]


def _kit(tmp_path: pathlib.Path) -> pathlib.Path:
    interview = tmp_path / "interview"
    interview.mkdir()
    (interview / "answers.md").write_text(ANSWERS_MD, encoding="utf-8")
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                    [(a, b, c, d, e, "x", "", "stated") for a, b, c, d, e in ROWS])
    con.commit()
    con.close()
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit, interview=interview)
    return kit


def test_package_copies_only_six_files_and_no_context(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    pkg = tmp_path / "blind"
    BLIND.build_blind_package(kit, pkg)

    md_files = sorted(p.name for p in pkg.glob("*.md"))
    assert "盲测三问.md" in md_files
    # No evidence digest, DB, interview copy, or raw export leaks into the package.
    assert not (pkg / "_evidence").exists()
    assert not list(pkg.glob("*.db"))
    assert not list(pkg.glob("*interview*"))

    questions = (pkg / "盲测三问.md").read_text(encoding="utf-8")
    for qid in ("Q1", "Q2", "Q3"):
        assert f"## {qid}" in questions

    expected = json.loads((pkg / ".expected.json").read_text(encoding="utf-8"))
    assert expected["mainline"]["count"] >= 1
    assert set(expected["principle"]["codes"]) >= {"1A", "2C", "3B"}
    assert expected["rule"]["count"] >= 1


def test_filled_sheet_matching_kit_passes(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    pkg = tmp_path / "blind"
    BLIND.build_blind_package(kit, pkg)
    expected = json.loads((pkg / ".expected.json").read_text(encoding="utf-8"))

    sheet = (
        "## Q1 当前主线\n"
        f"- 回答：{expected['mainline']['bullets'][0]}\n"
        "- 出处：01-身份与当前主线.md\n\n"
        "## Q2 判断准则\n"
        f"- 回答：{expected['principle']['bullets'][0]}\n"
        "- 出处：02-核心判断准则.md\n\n"
        "## Q3 硬规则 / 红线\n"
        f"- 回答：{expected['rule']['bullets'][0]}\n"
        "- 出处：03-硬规则与表达黑话.md\n"
    )
    result = BLIND.score_answers(expected, sheet)
    assert result["overall_passed"], result["questions"]
    assert all(q["passed"] for q in result["questions"].values())


def test_empty_or_guessed_sheet_fails(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    pkg = tmp_path / "blind"
    BLIND.build_blind_package(kit, pkg)
    expected = json.loads((pkg / ".expected.json").read_text(encoding="utf-8"))

    sheet = "## Q1 当前主线\n- 回答：档案里没有\n\n## Q2 判断准则\n- 回答：不知道\n\n## Q3 硬规则 / 红线\n- 回答：随便猜一个项目\n"
    result = BLIND.score_answers(expected, sheet)
    assert not result["overall_passed"]
    assert not result["questions"]["Q1"]["passed"]
    assert not result["questions"]["Q2"]["passed"]


def test_blind_blocked_until_reviewed(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    # Fresh kit defaults to pending_review; blind must be blocked like verify.
    rc = XH.blind(argparse.Namespace(kit=str(kit), out=str(tmp_path / "blind"), score=None))
    assert rc == 1
    XH._write_review_status(kit, XH.REVIEW_CONFIRMED)
    rc = XH.blind(argparse.Namespace(kit=str(kit), out=str(tmp_path / "blind"), score=None))
    assert rc == 0
