#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #56 regressions: semantic filtering + plain-language defaults.

Covers, with checkable rules (not "feels better"):
- rule_shape / case_shape predicates on real strings pulled from the before-fix
  real-729 draft;
- validator semantic audit flags padded/empty/non-rule/request sections;
- bootstrap emits at most one current mainline, no principle padding, no request case.

Encoding/mojibake diagnosis belongs to #55 / PR #64 (scripts/archive_io.py),
not this file.
"""

from __future__ import annotations

import importlib
import pathlib
import sqlite3
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

vk = importlib.import_module("03_validate_kit")
bootstrap = importlib.import_module("04_bootstrap_kit")


# --- Real strings from the before-fix real-729 draft (issue #56 evidence) ---

RULE_DIALOGUE = "我说叫你不要打断他们,让他们继续先做啊。"
RULE_TECH_EXCERPT = (
    "Charter/YuMincho/思源宋=OFL高设计 token(画布色/强调色≤5%/层级规则/行距)、"
    "14 个内嵌 SVG 图表、8 套模板结构⚠ 它出 PDF,不出可编辑 Word——"
    "和我们\"真·可编辑 .docx\"是冲突的WeasyPrintHTML/CSS→PDF 引擎BSD-3高若走 PDF 路线,它就是渲染器;"
)
RULE_SINGLE_TASK = "如果这 7 个视图是单独做的,那你就单独做生图素材,不要既做三视图又做这 7 个视图。"
RULE_MVP_CONDITION = "如果能加上对应的读取、写入等操作更好,但 MVP 阶段只需实现无限次读取,且必须是真的读取到里面的内容。"
RULE_SECOND_PERSON = "你安排完不要就后面就不要再宏大的一个叙事,你就要真实的,比如说将内容给了我。"

RULE_KEEP_PLAIN = "在事情没理清之前不要着急先做,我就是这样。"
RULE_KEEP_NO_COPY = "(c) 拒绝抄袭:不要直接抄别人,要真实地去看他们到底该怎么做。"
RULE_MCP = "无论形式是 MCP 还是 Skill,最终效果必须是能够无限调用。"
RULE_SECOND_PERSON = "你不能只说“前端要发给浏览器”,浏览器根本不知道这些东西。"
RULE_WISH = "我要的是顶尖设计,以及这里的话要有一种自然的过渡,不是那种很突然的,也不要一下子很大块的东西进去。"
RULE_DIVERGE = "一开始先发散,多尝试看哪个效果最好,后面再锁定其中一种,看能不能达到我们预期的效果。"

CASE_REQUEST = "所以我要解决就是这个问题啊,所以不然我要你怎么搜?"
CASE_BLAME = "我又没叫你进行去对应什么绕过啊,也没有进行对应欺骗啊,是你的提示词有问题。"
CASE_DEMAND = "我最终目标就是这个东西啊,你就是要完成这个,无论你用什么方法。"
CASE_KEEP = "踩坑了，之前停在最后一步没上线，后来改成先跑通再优化，最后完成了最小闭环。"


def test_rule_shape_rejects_dialogue_technical_task_and_mvp() -> None:
    for bad in (
        RULE_DIALOGUE, RULE_TECH_EXCERPT, RULE_SINGLE_TASK, RULE_MVP_CONDITION,
        RULE_SECOND_PERSON, RULE_MCP, RULE_WISH,
    ):
        ok, reason = vk.rule_shape(bad)
        assert not ok, f"should reject: {bad} ({reason})"
        assert reason != ""


def test_rule_shape_does_not_treat_question_verb_as_prohibition() -> None:
    ok, reason = vk.rule_shape(RULE_DIVERGE)
    assert not ok
    assert reason == "no-rule-verb"


def test_rule_shape_keeps_durable_self_rules() -> None:
    for good in (RULE_KEEP_PLAIN, RULE_KEEP_NO_COPY):
        ok, reason = vk.rule_shape(good)
        assert ok, f"should keep: {good} ({reason})"


def test_case_shape_rejects_request_and_blame() -> None:
    for bad in (CASE_REQUEST, CASE_BLAME, CASE_DEMAND):
        ok, reason = vk.case_shape(bad)
        assert not ok, f"should reject: {bad} ({reason})"


def test_case_shape_keeps_declarative_experience() -> None:
    ok, reason = vk.case_shape(CASE_KEEP)
    assert ok, reason


def _write_kit(kit: pathlib.Path, files: dict[str, str]) -> None:
    kit.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (kit / name).write_text(body, encoding="utf-8")


def _before_like_files() -> dict[str, str]:
    return {
        "AGENTS.md": "# AGENTS.md\n\n交接说明正文，足够长的正常档案内容。" * 3,
        "00-总入口索引.md": "# 00-总入口索引\n\n索引正文，足够长的正常档案内容。" * 3,
        "01-身份与当前主线.md": (
            "# 01-身份与当前主线\n\n## 二、当前主线候选\n\n"
            "- **候选-01** 我要做一个 3D 可视化项目。 ｜ 原文：「我要做一个 3D 可视化项目。」 ｜ 出处：_evidence/chat-lines.md:30\n"
            "- **候选-02** 我现在有一个排课的项目。 ｜ 原文：「我现在有一个排课的项目。」 ｜ 出处：_evidence/chat-lines.md:100\n"
        ),
        "02-核心判断准则.md": (
            "# 02-核心判断准则\n\n## 一、先验证再下结论\n\n"
            "- 本类样本不足：数据库中没有足够的「判断/取舍」原话。\n\n"
            "## 二、取舍顺序（候选）\n\n"
            "- 先确认目标与验收，再谈执行速度。\n"
            "- 先保真实与可复现，再谈漂亮表达。\n"
            "- 先做最小闭环，再扩规模。\n"
        ),
        "03-硬规则与表达黑话.md": (
            "# 03-硬规则与表达黑话\n\n## 一、硬规则候选\n\n"
            f"- **候选-01** {RULE_DIALOGUE} ｜ 原文：「{RULE_DIALOGUE}」 ｜ 出处：_evidence/chat-lines.md:76\n"
            f"- **候选-02** {RULE_TECH_EXCERPT} ｜ 原文：「{RULE_TECH_EXCERPT}」 ｜ 出处：_evidence/chat-lines.md:74\n"
        ),
        "04-反面案例清单.md": (
            "# 04-反面案例清单\n\n## 一、正例标本\n\n"
            f"- **候选-03** {CASE_REQUEST} ｜ 原文：「{CASE_REQUEST}」 ｜ 出处：_evidence/chat-lines.md:56\n"
        ),
    }


def test_audit_flags_before_like_kit(tmp_path: pathlib.Path) -> None:
    kit = tmp_path / "kit"
    _write_kit(kit, _before_like_files())
    findings = vk.audit_semantics(kit)
    codes = {f.code for f in findings}
    assert "SEMANTIC_MAINLINE_MULTIPLE" in codes, findings
    assert "SEMANTIC_PRINCIPLE_PADDING" in codes, findings
    assert "SEMANTIC_RULE_NONRULE" in codes, findings
    assert "SEMANTIC_CASE_REQUEST" in codes, findings


def test_audit_clean_on_fixed_kit(tmp_path: pathlib.Path) -> None:
    files = {
        "AGENTS.md": "# AGENTS.md\n\n交接说明正文，足够长的正常档案内容。" * 3,
        "00-总入口索引.md": "# 00-总入口索引\n\n索引正文，足够长的正常档案内容。" * 3,
        "01-身份与当前主线.md": (
            "# 01-身份与当前主线\n\n## 二、当前主线候选（最多 1 条，待本人确认）\n\n"
            "- **候选-01** 我要做一个 3D 可视化项目。 ｜ 原文：「我要做一个 3D 可视化项目。」 ｜ 出处：_evidence/chat-lines.md:30\n\n"
            "## 三、历史项目与曾经提到的方向（不是当前主线）\n\n- 暂无除当前主线外的其他方向候选。\n"
        ),
        "02-核心判断准则.md": (
            "# 02-核心判断准则\n\n## 一、有据判断（原话 + 出处）\n\n"
            "- 需访谈：数据库中没有足够的「判断/取舍」原话；请补访谈或更多聊天，不用推测或归纳填空。\n"
        ),
        "03-硬规则与表达黑话.md": (
            "# 03-硬规则与表达黑话\n\n## 一、硬规则候选\n\n"
            f"- **候选-01** {RULE_KEEP_PLAIN} ｜ 原文：「{RULE_KEEP_PLAIN}」 ｜ 出处：_evidence/chat-lines.md:77\n"
        ),
        "04-反面案例清单.md": (
            "# 04-反面案例清单\n\n## 一、正例标本\n\n"
            f"- **候选-01** {CASE_KEEP} ｜ 原文：「{CASE_KEEP}」 ｜ 出处：_evidence/chat-lines.md:58\n"
        ),
    }
    kit = tmp_path / "kit"
    _write_kit(kit, files)
    assert vk.audit_semantics(kit) == []


def test_audit_does_not_flip_structural_pass(tmp_path: pathlib.Path) -> None:
    """Semantic findings are advisory: VALIDATE_OK must not be hidden, but a
    structural pass must not be turned into a structural fail by the audit."""
    kit = tmp_path / "kit"
    _write_kit(kit, _before_like_files())
    ok, diags = vk.validate_kit(kit)
    assert ok is True  # structure itself is intact
    assert any(d.startswith("SEMANTIC_REVIEW:") for d in diags), diags
    assert any(d.startswith("SEMANTIC: [SEMANTIC_") for d in diags), diags


def _bootstrap_db(tmp_path: pathlib.Path) -> pathlib.Path:
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
         "踩坑了，之前停在最后一步没上线，后来改成先跑通再优化，最后完成了最小闭环。"),
        ("REC-0006", "20261103-100000-剪辑系统开发.md", "2026-11-03", "user",
         "这次跑通了，有效的做法是每步都给产物和退出码。"),
        ("REC-0007", "20261104-100000-技能安装.md", "2026-11-04", "user",
         "记住，禁止替本人签字，不确定的边界要标出处。"),
        # Noise that must be filtered out of rule/case slots.
        ("REC-0008", "20261105-100000-排课项目.md", "2026-11-05", "user",
         "如果这 7 个视图是单独做的，那你就单独做生图素材，不要既做三视图又做这 7 个视图。"),
        ("REC-0009", "20261105-100000-检索咨询.md", "2026-11-05", "user",
         "所以我要解决就是这个问题啊，所以不然我要你怎么搜？"),
    ]
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                    [(a, b, c, d, e, "x", "", "stated") for a, b, c, d, e in rows])
    con.commit()
    con.close()
    return db


def test_bootstrap_emits_clean_semantic_kit(tmp_path: pathlib.Path) -> None:
    db = _bootstrap_db(tmp_path)
    kit = tmp_path / "kit"
    res = bootstrap.build_kit(db, kit)
    assert res["validate_ok"], res["validate_messages"]

    text01 = (kit / "01-身份与当前主线.md").read_text(encoding="utf-8")
    mainline_section = text01.split("## 二、当前主线候选")[1].split("## 三、")[0]
    assert mainline_section.count("- **候选") <= 1

    text02 = (kit / "02-核心判断准则.md").read_text(encoding="utf-8")
    for padding in ("先确认目标与验收，再谈执行速度", "先保真实与可复现，再谈漂亮表达", "先做最小闭环，再扩规模"):
        assert padding not in text02

    text04 = (kit / "04-正反例避坑账.md").read_text(encoding="utf-8")
    assert "怎么搜" not in text04

    assert vk.audit_semantics(kit) == []
