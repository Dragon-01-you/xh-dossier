#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for `05b_l2_theme.py` — cross-conversation difference mining."""

import importlib
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
theme = importlib.import_module("05b_l2_theme")
l2 = importlib.import_module("05_deep_backfill")


def _profiles() -> dict[str, str]:
    return {name: f"# {name}\n普通档案，未引用任何记录。\n" for name in l2.PROFILE_FILES}


def test_requires_two_docs():
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "我想看真正的一手原型，而不是别人官网上的东西。"},
    ]
    cands, _ = theme.mine_themes(recs, _profiles(), l2.FirstPassIndex())
    assert cands == []


def test_same_file_two_hits_is_rejected():
    """Two hits in one conversation are not "cross-conversation"."""
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "我想看真正的一手原型，而不是别人官网上的东西。"},
        {"rec_id": "REC-0002", "source_file": "a.md", "created_at": "2026-01-02",
         "role": "user", "content": "我要真实报告的一手原文，不要拿总结代替。"},
    ]
    cands, _ = theme.mine_themes(recs, _profiles(), l2.FirstPassIndex())
    assert cands == []


def test_cross_doc_theme_produced():
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "我想看真正的一手原型，而不是别人官网上的东西。"},
        {"rec_id": "REC-0002", "source_file": "b.md", "created_at": "2026-01-02",
         "role": "user", "content": "我要真实报告的一手原文，不要拿总结代替。"},
    ]
    cands, _ = theme.mine_themes(recs, _profiles(), l2.FirstPassIndex())
    assert len(cands) == 1
    assert cands[0].signal == "hard_rule"
    assert cands[0].needs_llm is True
    assert "[待确认]" not in cands[0].excerpt
    assert "a.md" in cands[0].source_file and "b.md" in cands[0].source_file
    assert cands[0].phrase_hits == 2


def test_question_and_ai_directed_skipped():
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "你可以看一下这个一手资料吗？"},
        {"rec_id": "REC-0002", "source_file": "b.md", "created_at": "2026-01-02",
         "role": "user", "content": "你看一下这个真实报告，给我一手原文。"},
    ]
    cands, _ = theme.mine_themes(recs, _profiles(), l2.FirstPassIndex())
    assert cands == []


def test_covered_rec_skipped():
    profiles = _profiles()
    profiles["03-硬规则与表达黑话.md"] += "\nREC-0001\n"
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "我想看真正的一手原型，而不是别人官网上的东西。"},
        {"rec_id": "REC-0002", "source_file": "b.md", "created_at": "2026-01-02",
         "role": "user", "content": "我要真实报告的一手原文，不要拿总结代替。"},
    ]
    cands, dropped = theme.mine_themes(recs, profiles, l2.FirstPassIndex())
    assert not any(c.rec_id == "REC-0001" for c in cands)
    assert any(d["reason"] == "C0_covered_by_profile" for d in dropped)


def test_secret_record_skipped():
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "本地跑不了，接 API，SecretKey=abcdefghijklmnopqrstuvwxyz123456"},
        {"rec_id": "REC-0002", "source_file": "b.md", "created_at": "2026-01-02",
         "role": "user", "content": "本地太卡了，我想接 API 跑。"},
    ]
    cands, dropped = theme.mine_themes(recs, _profiles(), l2.FirstPassIndex())
    assert any(d["reason"] == "secret_redacted_record" for d in dropped)
