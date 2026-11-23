#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #1 + #3: deep-hook follow-up, language-following, custom options, unbundled choices."""

from __future__ import annotations

import pathlib
import re
import sys
from importlib import import_module

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sim = import_module("interview_sim")

skill = (REPO / "skills" / "onboarding-interviewer" / "SKILL.md").read_text(encoding="utf-8")
prompt = (REPO / "prompts" / "01_web_ai_interviewer.md").read_text(encoding="utf-8")


def test_deep_hook_follow_up_in_skill():
    assert "深钩追问" in skill
    assert "带日期" in skill and "代价" in skill


def test_emotional_safety_framing():
    assert "情绪安全感" in skill and "说错不扣分" in skill


def test_language_following_in_both():
    assert "语言跟随" in skill
    assert "英文问→英文答" in prompt


def test_custom_option_in_both():
    assert "D` 自定义" in skill or "D 自定义" in skill
    assert "D 自定义位" in prompt


def test_q3_unbundled():
    # "不经同意改文件" and "AI 代做算能力" must be separate options.
    line_c = next(l for l in skill.splitlines() if l.strip().startswith("- `C` 不经本人同意"))
    line_d = next(l for l in skill.splitlines() if l.strip().startswith("- `D` 把 AI 代做"))
    assert "删改原文件" in line_c and "代做" not in line_c
    assert "代做成果" in line_d and "删改原文件" not in line_d


# ---------------------------------------------------------------------------
# Blocker B1: explicit custom slot on every closed question, rounds 1~6.
# ---------------------------------------------------------------------------

def _bank():
    return sim.parse_question_bank(skill)


def test_custom_slot_on_every_closed_question_all_rounds():
    """每道封闭题末项必须是显式自定义 / 可补充位（解析题库，不查零散字样）。"""
    closed_count = 0
    for rnd in _bank():
        for q in rnd.questions:
            if q.open_question:
                continue
            closed_count += 1
            assert q.custom_option is not None, f"第 {rnd.index} 轮题 {q.index} 缺自定义位"
            assert q.custom_option.letter == q.options[-1].letter
    # 题库共 6 轮 × 3 题，其中开放题 4 道（R3Q1、R5Q2、R6Q1、R6Q2）。
    assert closed_count == 14


def test_rounds_2_to_6_each_have_explicit_custom_slot():
    """B1 回归：第 2~6 轮每轮至少一道封闭题带显式自定义位（旧版只在第 1 轮）。"""
    bank = _bank()
    for rnd in bank[1:]:
        closed = [q for q in rnd.questions if not q.open_question]
        assert closed, f"第 {rnd.index} 轮没有封闭题"
        assert any(q.custom_option is not None for q in closed), f"第 {rnd.index} 轮缺自定义位"


# ---------------------------------------------------------------------------
# Blocker B2: positive/negative case collection starts from round 2.
# ---------------------------------------------------------------------------

def test_early_case_collection_in_rounds_2_to_4():
    sections = re.split(r"### 第 \d 轮题库", skill)
    # sections[0] 为前言，sections[1..6] 对应第 1~6 轮。
    for round_no in (2, 3, 4):
        assert "正反例滚动账" in sections[round_no], f"第 {round_no} 轮缺滚动正反例采集位"
    assert "从第 2 轮起" in skill
    assert "从第 2 轮起" in prompt


# ---------------------------------------------------------------------------
# Simulator behavioral tests: custom text adopted, early cases land in 04 kit.
# ---------------------------------------------------------------------------

def _transcript() -> dict:
    return {
        "rounds": [
            {  # 第 1 轮
                "answers": [
                    {"question": 1, "choice": "B"},
                    {"question": 2, "choice": "D", "custom": "先打生活比方再贴命令，代码只在最后给"},
                    {"question": 3, "choice": "F", "custom": "不接受同一件事被反复追问三遍"},
                ],
                "cases": [
                    {"kind": "positive", "text": "2026-10-28 开工前先定死验收标准，两小时交付没有返工"},
                ],
            },
            {  # 第 2 轮
                "answers": [
                    {"question": 1, "choice": "B"},
                    {"question": 2, "choice": "D", "custom": "Obsidian 本地库，只读参考堆单独放 vault-ref 目录"},
                    {"question": 3, "choice": "B"},
                ],
                "cases": [
                    {"kind": "negative", "text": "2026-10-12 静态小工具停在最后百分之十改按钮对齐，拖了四天错过截止"},
                ],
            },
            {  # 第 3 轮
                "answers": [
                    {"question": 1, "text": "当前主线：把多窗口上下文收敛成六份可迁移 Memory，卡在新窗口重复解释"},
                    {"question": 2, "choice": "A"},
                    {"question": 3, "choice": "B"},
                ],
                "cases": [
                    {"kind": "negative", "text": "曾瞎堆三个月大计划没执行，两周后全部搁置，教训是先跑最小闭环"},
                ],
            },
            {  # 第 4 轮
                "answers": [
                    {"question": 1, "choice": "A"},
                    {"question": 2, "choice": "C"},
                    {"question": 3, "choice": "D", "custom": "同一卡点超过二十分钟没进展，先停手写三行卡点再换路线"},
                ],
                "cases": [],
            },
            {  # 第 5 轮
                "answers": [
                    {"question": 1, "choice": "A"},
                    {"question": 2, "text": "曾用名小墨，2026-10-22 起对外统一称呼林墨"},
                    {"question": 3, "choice": "A"},
                ],
                "cases": [],
            },
            {  # 第 6 轮
                "answers": [
                    {"question": 1, "text": "补记：先写验收标准再动手的做法继续固化"},
                    {"question": 2, "text": "补记：拖到最后百分之十的问题继续拦停"},
                    {"question": 3, "choice": "A"},
                ],
                "cases": [],
            },
        ]
    }


def test_simulator_adopts_custom_values_into_target_files():
    result = sim.run_interview(skill, _transcript())
    by_file = {rec["target_file"]: rec for rec in result["records"]}

    # 第 1 轮两条自定义原话必须逐字进入 AGENTS.md。
    agents = result["kit"]["AGENTS.md"]
    assert "先打生活比方再贴命令，代码只在最后给" in agents
    assert "不接受同一件事被反复追问三遍" in agents
    # 第 2 轮自定义原话进入 00 索引；第 4 轮自定义原话进入 02 准则。
    assert "Obsidian 本地库，只读参考堆单独放 vault-ref 目录" in result["kit"]["00-总入口索引.md"]
    assert "同一卡点超过二十分钟没进展，先停手写三行卡点再换路线" in result["kit"]["02-核心判断准则.md"]

    # 每条采纳记录都能在对应档案里找回原话（不是摆设）。
    for rec in result["records"]:
        for custom in rec["adopted_customs"]:
            assert custom in result["kit"][rec["target_file"]]
    assert len(by_file["AGENTS.md"]["adopted_customs"]) == 2
    assert len(by_file["00-总入口索引.md"]["adopted_customs"]) == 1
    assert len(by_file["02-核心判断准则.md"]["adopted_customs"]) == 1


def test_simulator_merges_round_1_to_3_cases_into_final_kit():
    result = sim.run_interview(skill, _transcript())
    kit04 = result["kit"]["04-正反例避坑账.md"]

    early_texts = [
        "2026-10-28 开工前先定死验收标准，两小时交付没有返工",
        "2026-10-12 静态小工具停在最后百分之十改按钮对齐，拖了四天错过截止",
        "曾瞎堆三个月大计划没执行，两周后全部搁置，教训是先跑最小闭环",
    ]
    for text in early_texts:
        assert text in kit04, f"前 3 轮采集的案例未进入最终 04 档案：{text}"
    # 案例带来源轮次标注。
    assert "[第 1 轮]" in kit04 and "[第 2 轮]" in kit04 and "[第 3 轮]" in kit04


def test_simulator_rejects_custom_choice_without_text():
    bad = _transcript()
    bad["rounds"][0]["answers"][1] = {"question": 2, "choice": "D", "custom": "   "}
    with pytest.raises(sim.SimError, match="自定义位"):
        sim.run_interview(skill, bad)


def test_simulator_rejects_unknown_choice_letter():
    bad = _transcript()
    bad["rounds"][1]["answers"][0] = {"question": 1, "choice": "Z"}
    with pytest.raises(sim.SimError, match="不在题库"):
        sim.run_interview(skill, bad)


def test_every_round_has_custom_option():
    # B1: D custom option must exist in rounds 2-6 too, not only round 1.
    sections = skill.split("### 第 ")
    assert len(sections) >= 7
    for sec in sections[2:7]:  # rounds 2..6
        assert "- `D` 自定义" in sec, sec[:40]


def test_open_example_slot_every_round():
    assert "每轮末尾的开放位" in skill
    assert "不要把所有正反例采集都压到第 6 轮" in skill


# ---------------------------------------------------------------------------
# Issue #83: paste/reference existing life narrative; Stage 3 reflow prefers
# already-collected context before re-verifying [待确认] items.
# ---------------------------------------------------------------------------

def test_history_narrative_entry_in_skill_and_prompt():
    for token in ("粘贴", "引用", "已有上下文"):
        assert token in skill, f"SKILL.md 缺历史叙述入口字样：{token}"
        assert token in prompt, f"网页提示词缺历史叙述入口字样：{token}"
    assert "优先检索" in skill and "已有上下文" in skill


# ---------------------------------------------------------------------------
# Issue #84: missing target product triggers a re-ask anchored to this round's
# answer; previous-round context is carried into the next question.
# ---------------------------------------------------------------------------

def test_product_gate_and_context_carryover_in_skill_and_prompt():
    for token in ("重问", "上一轮", "产物门禁"):
        assert token in skill, f"SKILL.md 缺门禁/带入规则：{token}"
    assert "上一轮" in prompt and "重问" in prompt


def test_sim_records_carryover_and_reask_gate():
    bad = _transcript()
    bad["rounds"][1]["carryover"] = "上一轮定了严谨合伙人站位"
    bad["rounds"][2]["product_gate"] = "reask"
    result = sim.run_interview(skill, bad)
    by_round = {rec["round"]: rec for rec in result["records"]}

    assert by_round[2]["carryover"] == "上一轮定了严谨合伙人站位"
    assert "带入上一轮要点" in result["kit"]["00-总入口索引.md"]
    assert by_round[3]["product_gate"] == "reask"
    assert "产物门禁" in result["kit"]["01-身份与当前主线.md"]


def test_sim_rejects_unknown_product_gate():
    bad = _transcript()
    bad["rounds"][0]["product_gate"] = "nope"
    with pytest.raises(sim.SimError, match="产物门禁"):
        sim.run_interview(skill, bad)


# ---------------------------------------------------------------------------
# Issue #85: identity branches — students / employed / parallel projects / no
# core project — must appear in the skill, and the simulator must walk a
# non-default branch.
# ---------------------------------------------------------------------------

def test_identity_branches_in_skill():
    for branch in ("学生", "在职", "多项目并行", "暂无核心项目"):
        assert branch in skill, f"SKILL.md 缺身份分支：{branch}"
    assert "不存在“人人都有唯一核心项目”" in skill or "唯一核心项目" in skill


def test_sim_walks_non_default_identity_branch():
    candidate = _transcript()
    candidate["rounds"][2]["identity"] = "学生"
    result = sim.run_interview(skill, candidate)
    r3 = next(rec for rec in result["records"] if rec["round"] == 3)
    assert r3["identity"] == "学生"
    assert "身份分支：学生" in result["kit"]["01-身份与当前主线.md"]


def test_sim_rejects_unknown_identity_branch():
    bad = _transcript()
    bad["rounds"][2]["identity"] = "自由职业外星人"
    with pytest.raises(sim.SimError, match="身份分支"):
        sim.run_interview(skill, bad)


# ---------------------------------------------------------------------------
# Issue #86: address → identity/stage → concrete daily/weekly slots; the old
# vague "排满" wording is gone.
# ---------------------------------------------------------------------------

def test_collection_order_and_concrete_slots():
    assert "先问称呼" in skill or "开场先收" in skill
    assert "每日" in skill and "每周" in skill
    assert "乱排满" not in skill
    assert "排满" not in skill or "不要让 AI 把日程排满" in skill
    # Prompt mirrors the order: address first, identity before time slots.
    assert "称呼" in prompt and "身份" in prompt


# ---------------------------------------------------------------------------
# Issue #87: plain-language preamble (what / success looks like / what if stuck)
# and goal-driven questioning instead of a fixed script.
# ---------------------------------------------------------------------------

def test_plain_language_preamble_and_goal_driven():
    for token in ("成功", "失败怎么办", "前置说明"):
        assert token in skill, f"SKILL.md 缺小白前置说明：{token}"
    assert "按阶段目标出题" in skill or "目标" in skill
    assert "示例" in skill and "固定题库" in skill
    assert "成功" in prompt and "失败怎么办" in prompt
