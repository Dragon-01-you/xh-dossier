#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #94: pasted third-party material, questions and task-content sentences
must not become A-level identity / principle / rule candidates; the L2 pending
zone skips question excerpts; the validator surfaces an advisory (which never
flips the structural pass).
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
from importlib import import_module

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

boot = import_module("04_bootstrap_kit")
backfill = import_module("05_deep_backfill")
l2 = import_module("08_l2_apply")
validator = import_module("03_validate_kit")

# Reproduced from the issue evidence (chat-lines.md:37 / :114 / :95).
THIRD_PARTY_PRINCIPLE = (
    "(二) 人生选择与行动哲学核心原则:\"今朝有酒今朝醉,我的快乐最重要\""
    "(作为过去五十年选择的核心标准)"
)
QUESTION_IDENTITY = "我目前不太清楚它是以什么形式存储的…你可以看一下"
TASK_CONTENT_RULE = "我就想用 3D 建模应用程序…把冰屋渲染出来"

OWN_PRINCIPLE = "判断原则是先验证再下结论，先做最小闭环，再扩规模。"
OWN_RULE = "记住，禁止替本人签字，不确定的边界要标出处。"
OWN_IDENTITY = "我是个人开发者，我在做一个 3D 可视化项目。"


def test_third_party_pasted_philosophy_rejected_as_principle() -> None:
    assert boot.candidate_sentence(THIRD_PARTY_PRINCIPLE, "principle") == ""


def test_question_rejected_as_identity() -> None:
    assert boot.candidate_sentence(QUESTION_IDENTITY, "identity") == ""


def test_task_content_rejected_as_rule() -> None:
    assert boot.candidate_sentence(TASK_CONTENT_RULE, "rule") == ""


def test_own_declarative_statements_still_pass() -> None:
    assert boot.candidate_sentence(OWN_PRINCIPLE, "principle")
    assert boot.candidate_sentence(OWN_RULE, "rule")
    assert boot.candidate_sentence(OWN_IDENTITY, "identity")


def test_backfill_classifies_question_and_pasted_material_as_non_personal() -> None:
    ok, reason = backfill.classify_narrative(QUESTION_IDENTITY)
    assert ok is False and reason == "non_personal:question"
    ok, reason = backfill.classify_narrative(
        "安先生个人简介：教育经历……他认为人生最重要的是快乐"
    )
    assert ok is False and reason == "non_personal:ai_or_material"
    ok, _ = backfill.classify_narrative(
        "踩坑了，之前停在最后一步没上线，后来改成先跑通再优化。"
    )
    assert ok is True


def _db(tmp_path: pathlib.Path) -> pathlib.Path:
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    rows = [
        ("REC-0001", "项目.md", "2026-11-01", "user", OWN_IDENTITY),
        ("REC-0002", "项目.md", "2026-11-02", "user", OWN_RULE),
        ("REC-0003", "项目.md", "2026-11-03", "user", OWN_PRINCIPLE),
        ("REC-0004", "项目.md", "2026-11-04", "user",
         "踩坑了，之前停在最后一步没上线，后来改成先跑通再优化。"),
    ]
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                    [(a, b, c, d, e, "x", "", "stated") for a, b, c, d, e in rows])
    con.commit()
    con.close()
    return db


def test_l2_apply_skips_question_excerpts(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    kit = tmp_path / "kit"
    boot.build_kit(db, kit)

    l2dir = tmp_path / "l2"
    patches = l2dir / "l2_profile_patches"
    patches.mkdir(parents=True)
    question_excerpt = "这条是不是必须得签字，还是说什么"
    declarative = "我的项目是芯火知识库，必须保留原文出处，不要编造没有发生的事。"
    (patches / "03-硬规则与表达黑话.md.patch.md").write_text(
        "### L2-0001 [待确认] [REC-0002]\n"
        f"- **原文摘录**：> {declarative}\n"
        "### L2-0002 [待确认] [REC-0003]\n"
        f"- **原文摘录**：> {question_excerpt}\n",
        encoding="utf-8",
    )

    out = tmp_path / "kit_next"
    res = l2.apply_unsigned(kit, l2dir, out)
    assert res["applied"] == 1
    assert res["question_skipped"] == 1
    text = (out / "03-硬规则与表达黑话.md").read_text(encoding="utf-8")
    assert question_excerpt not in text
    assert "L2-0002" not in text


def test_validator_advisory_flags_question_and_pasted_material(tmp_path: pathlib.Path) -> None:
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "02-核心判断准则.md").write_text(
        "# 02 · 核心判断准则\n\n"
        "## 准则候选\n\n"
        f"- **候选-01** ｜ 原文：「{QUESTION_IDENTITY}」 ｜ 出处：_evidence/chat-lines.md:114\n"
        f"- **候选-02** ｜ 原文：「{THIRD_PARTY_PRINCIPLE}」 ｜ 出处：_evidence/chat-lines.md:37\n",
        encoding="utf-8",
    )
    findings = validator.audit_semantics(kit)
    codes = {f.code for f in findings}
    assert "SEMANTIC_QUESTION_CANDIDATE" in codes
    assert "SEMANTIC_PASTED_MATERIAL" in codes

def test_validator_advisory_scans_all_three_profile_docs(tmp_path: pathlib.Path) -> None:
    # Regression: the advisory scan must not return after the first profile doc.
    kit = tmp_path / "kit"
    kit.mkdir()
    for fkey in ("01-身份与当前主线.md", "02-核心判断准则.md", "03-硬规则与表达黑话.md"):
        (kit / fkey).write_text(
            "# 标题\n\n- **候选-01** ｜ 原文：「我目前不太清楚它是什么形式，你可以看一下」 ｜ 出处：x:1\n",
            encoding="utf-8",
        )
    findings = validator.audit_semantics(kit)
    flagged = {f.file for f in findings if f.code == "SEMANTIC_QUESTION_CANDIDATE"}
    assert flagged == {
        "01-身份与当前主线.md", "02-核心判断准则.md", "03-硬规则与表达黑话.md",
    }