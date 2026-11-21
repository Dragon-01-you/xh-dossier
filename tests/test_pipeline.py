# -*- coding: utf-8 -*-
"""Comprehensive unit and end-to-end tests for the AI Onboarding Kit scripts."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from importlib import import_module

mod_clean = import_module("01_clean_and_index")
mod_match = import_module("02_four_way_match")
mod_val = import_module("03_validate_kit")


def test_clean_dedup_and_keyword_search(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "cold.db"
    stats = mod_clean.clean_and_index(REPO_ROOT / "examples" / "sample_raw", db_path)

    # sample_raw deliberately includes 1 exact duplicate across json & md
    assert stats["total_raw"] >= 8
    assert stats["dedup_skipped"] >= 1
    assert stats["indexed"] == stats["total_raw"] - stats["dedup_skipped"]

    # FTS5 trigram search (>= 3 chars)
    long_hits = mod_clean.search_keyword(db_path, "验收标准")
    assert len(long_hits) >= 2

    # LIKE fallback (< 3 chars)
    short_hits = mod_clean.search_keyword(db_path, "记错")
    assert len(short_hits) >= 1
    assert any("REC-" in h["rec_id"] for h in short_hits)


def test_chunk_text_preserves_long_tails() -> None:
    long_body = "甲" * 500 + "乙" * 500 + "核心尾巴词"
    chunks = mod_match.chunk_text(long_body, size=500, overlap=80)
    assert len(chunks) == 3
    assert "核心尾巴词" in chunks[-1]
    assert chunks[0][-80:] == chunks[1][:80]
    assert chunks[1][-80:] == chunks[2][:80]


def test_mean_centering_reduces_baseline_anisotropy() -> None:
    texts = [
        "今天讨论自动化脚本与单元测试流水线",
        "昨天调试网页导出插件开启开发者模式",
        "每周复盘发现总是拖延到截止前才交付",
        "整理个人核心判断准则与反面避坑账本",
    ]
    raw_vecs, _ = mod_match.build_tfidf_vectors(texts)
    centered, _mu = mod_match.mean_center_and_normalize(raw_vecs)

    raw_sims = [mod_match.cosine_sim(raw_vecs[i], raw_vecs[j]) for i in range(len(texts)) for j in range(i + 1, len(texts))]
    cen_sims = [mod_match.cosine_sim(centered[i], centered[j]) for i in range(len(texts)) for j in range(i + 1, len(texts))]
    assert sum(cen_sims) / len(cen_sims) < sum(raw_sims) / len(raw_sims)


def test_guardrails_block_subject_inversion_and_negation() -> None:
    ok_subj, reason_subj = mod_match.apply_guardrails("今天是我没听懂你讲的协程概念，请打比方", "ai_misunderstood_user")
    assert not ok_subj
    assert "subject_object_inversion" in reason_subj

    ok_real, _ = mod_match.apply_guardrails("你还是没理解我要的是先原理后代码", "ai_misunderstood_user")
    assert ok_real

    ok_neg, reason_neg = mod_match.apply_guardrails("先不要帮我改代码，我自己先看日志", "affirmative_action")
    assert not ok_neg
    assert "negation_marker" in reason_neg


def test_end_to_end_four_way_pipeline(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "demo.db"
    out_md = tmp_path / "backfill_candidates.md"
    mod_clean.clean_and_index(REPO_ROOT / "examples" / "sample_raw", db_path)

    report = mod_match.run_four_way_pipeline(db_path, ["记错", "验收"])
    md = mod_match.render_backfill_markdown(report)
    out_md.write_text(md, encoding="utf-8")

    assert report["records"] >= 7
    assert "Way 1" in md and "Way 3" in md and "Way 4" in md
    assert "[已拦截" in md
    assert "[待确认]" in md


def test_validate_kit_templates_and_strict_mode(tmp_path: pathlib.Path) -> None:
    ok_non_strict, _ = mod_val.validate_kit(REPO_ROOT / "templates", strict=False)
    assert ok_non_strict

    ok_strict_tpl, msgs_tpl = mod_val.validate_kit(REPO_ROOT / "templates", strict=True)
    assert not ok_strict_tpl
    assert any("UNFILLED" in m for m in msgs_tpl)

    # Complete clean user kit passes strict mode
    clean_kit = tmp_path / "clean_kit"
    clean_kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (clean_kit / fname).write_text(f"# {fname}\n\n" + "这是经过核实并亲口拍板的真实个人核心记录条目，用于测试验证完整性。" * 3, encoding="utf-8")
    ok_clean, msgs_clean = mod_val.validate_kit(clean_kit, strict=True)
    assert ok_clean, msgs_clean
