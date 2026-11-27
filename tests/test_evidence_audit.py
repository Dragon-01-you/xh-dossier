#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Evidence-class tests for `05b_l2_theme.py` (issue #147).

The ticket's real failure: a candidate advertised `docs=6` while only one
conversation actually contained the user's own on-topic sentence — the rest
were pasted prompt templates. These tests lock the fix:

- a pasted prompt (formatting words, no first person) is `prompt_or_external`;
- `personal_docs` counts only personal on-topic source conversations;
- `source_file_hits` keeps the raw file-hit count, separately;
- a theme without enough personal evidence is rejected, with the counts kept.
"""

import importlib
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
theme = importlib.import_module("05b_l2_theme")
l2 = importlib.import_module("05_deep_backfill")


def _profiles() -> dict[str, str]:
    return {name: f"# {name}\n普通档案，未引用任何记录。\n" for name in l2.PROFILE_FILES}


def test_prompt_template_is_external_material():
    assert theme.classify_evidence(
        "报告需要在10000～30000字之间，语言尽量通俗，不要堆砌资料"
    ) == "prompt_or_external"
    assert theme.classify_evidence("输出格式：1. 背景 2. 结论") == "prompt_or_external"


def test_rule_sentence_stays_personal():
    assert theme.classify_evidence("我要求所有结论都必须能回到原文") == "personal_on_topic"
    assert theme.classify_evidence("不要拿总结冒充原文") == "personal_on_topic"


def test_prompt_heavy_theme_is_rejected_with_counts():
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "报告需要在10000～30000字之间，语言尽量通俗，不要堆砌资料"},
        {"rec_id": "REC-0002", "source_file": "b.md", "created_at": "2026-01-02",
         "role": "user", "content": "我说过多少次了，必须说人话，别整黑话这一套。"},
    ]
    cands, dropped = theme.mine_themes(recs, _profiles(), l2.FirstPassIndex())
    assert cands == []
    rejection = next(d for d in dropped if d["reason"] == "C2_insufficient_personal_evidence")
    assert rejection["personal_docs"] == 1
    assert rejection["source_file_hits"] == 2
    assert rejection["classified"]["prompt_or_external"] >= 1


def test_two_personal_docs_still_produce_candidate():
    recs = [
        {"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
         "role": "user", "content": "我想看真正的一手原型，而不是别人官网上的东西。"},
        {"rec_id": "REC-0002", "source_file": "b.md", "created_at": "2026-01-02",
         "role": "user", "content": "我要真实报告的一手原文，不要拿总结代替。"},
    ]
    cands, _ = theme.mine_themes(recs, _profiles(), l2.FirstPassIndex())
    assert len(cands) == 1
    assert "personal_docs=2" in cands[0].evidence
    assert "source_file_hits=2" in cands[0].evidence
