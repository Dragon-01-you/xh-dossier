#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #6 real layer-2 deep backfill (design doc §6)."""

import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import importlib  # noqa: E402

l2 = importlib.import_module("05_deep_backfill")


# --- §4.2 narrative perspective gate ---

def test_prompt_prefix_rejected():
    ok, reason = l2.classify_narrative("你是一名全栈工程师，请帮我做一个AI博主定位方案" * 2)
    assert not ok and "prompt_prefix" in reason


def test_podcast_summary_rejected():
    ok, reason = l2.classify_narrative("我贴一份📑 智能总结，内容Type播客稿，感谢收听，我想听你的意见")
    assert not ok and "ai_or_material" in reason


def test_personal_experience_kept():
    ok, reason = l2.classify_narrative("上次我做完那个静态小工具一直没发出去，拖了四天，结果错过社群截止")
    assert ok and reason == "personal"


def test_no_first_person_rejected():
    ok, reason = l2.classify_narrative("这个工具支持多种格式导出，包含markdown和json，适用于多种场景" * 2)
    assert not ok


# --- §4.3 sentence-level negation / subject-object ---

def test_negation_at_sentence_head_filtered():
    r = l2.sentence_signals(["先不要帮我改完一直没发出去那版网页，别直接替我重写"])
    assert r["complaint"] == 0 and r["mistake"] == 0
    assert "negation" in r["filtered"]


def test_subject_object_inversion_filtered():
    # Pure user-side confusion (no AI-missed-user cue) must be filtered.
    r = l2.sentence_signals(["我没听懂这个概念，我自己再想想"])
    assert "subject_object_inversion" in r["filtered"]


def test_first_person_complaint_counted():
    r = l2.sentence_signals(["我每次都要重新解释一遍，实在太累了"])
    assert r["complaint"] >= 1


# --- §4.1 stopwords / cross-document phrases ---

def test_auxiliary_words_not_mined():
    recs = [
        {"source_file": "a.md", "content": "我觉得你可以看一下这个，可以看一下那个"},
        {"source_file": "b.md", "content": "你可以看一下这里，我觉得可以"},
    ]
    phrases = l2.mine_repeated_phrases(recs)
    assert all("可以看一下" not in p.phrase and "我觉得" not in p.phrase for p in phrases)


def test_content_phrase_across_docs_mined():
    # The SAME content phrase must appear in >=2 different source files.
    recs = [
        {"source_file": "a.md", "content": "我开工先定验收标准真的防返工，一次只改一个文件。"},
        {"source_file": "b.md", "content": "我这次也先定验收标准，结果两小时就交付了。"},
    ]
    phrases = l2.mine_repeated_phrases(recs)
    assert any("验收标准" in p.phrase for p in phrases)


# --- §3.1 mandatory inputs ---

def test_missing_first_pass_rejected(tmp_path):
    db = tmp_path / "x.db"
    db.touch()
    # Build a minimal valid profile dir so load_profiles passes and the test
    # actually reaches the mandatory first-pass check.
    for name in l2.PROFILE_FILES:
        (tmp_path / name).write_text("# " + name + "\n普通档案内容\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="MISSING_FIRST_PASS_INPUT"):
        l2.run_deep_backfill(tmp_path, tmp_path / "nope.md", db, tmp_path / "out")


# --- signing state machine ---

def test_state_machine_rejects_illegal_jump(tmp_path):
    ledger = tmp_path / "l.jsonl"
    with pytest.raises(ValueError, match="ILLEGAL_STATE_TRANSITION"):
        l2.update_review(ledger, "L2-0001", "archived", "芯火")


def test_sign_requires_reviewer(tmp_path):
    ledger = tmp_path / "l.jsonl"
    l2.update_review(ledger, "L2-0001", "reviewed", "agent")  # pending->reviewed
    with pytest.raises(ValueError, match="SIGNATURE_REQUIRES_REVIEWER"):
        l2.update_review(ledger, "L2-0001", "signed", "")


def test_full_sign_flow(tmp_path):
    ledger = tmp_path / "l.jsonl"
    l2.update_review(ledger, "L2-0001", "reviewed", "agent-a")
    row = l2.update_review(ledger, "L2-0001", "signed", "芯火")
    assert row["status"] == "signed" and row["reviewer"] == "芯火" and row["signed_at"]


def test_apply_signed_requires_confirm(tmp_path):
    res = l2.apply_signed(tmp_path, tmp_path, {}, confirm=False)
    assert res["applied"] == 0 and res["reason"] == "NEEDS_CONFIRM"


def test_agents_never_auto_written():
    # AGENTS.md must be read-only for the auto path.
    assert l2.AGENTS_READ_ONLY is True


# --- coverage decision C0~C3 ---

def test_covered_rec_not_produced(tmp_path):
    profiles = {"AGENTS.md": "REC-0001 already told"}
    cov = l2.build_coverage_index(profiles)
    fp = l2.FirstPassIndex(pending_rec_ids=set(), claims={})
    recs = [{"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
             "role": "user", "content": "我上次做完没发出去，实在太累了"}]
    cands, dropped = l2.coverage_decide(recs, cov, fp)
    assert not cands
    assert any(d["reason"] == "C0_covered_by_profile" for d in dropped)


def test_l1_pending_is_cross_ref_not_duplicate(tmp_path):
    cov = l2.CoverageIndex()
    fp = l2.FirstPassIndex(pending_rec_ids={"REC-0002"}, claims={})
    recs = [{"rec_id": "REC-0002", "source_file": "a.md", "created_at": "2026-01-01",
             "role": "user", "content": "我每次都要重新解释，实在太累，反复如此"}]
    cands, _ = l2.coverage_decide(recs, cov, fp)
    assert len(cands) == 1 and cands[0].cross_ref == "L1"
