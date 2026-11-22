# -*- coding: utf-8 -*-
"""Issue #2 Bug C: UNCERTAIN_PROSE channel catches natural-language doubt.

The literal `[待确认]` marker alone misses prose like "记不清当时到底有没有
发出去". These tests pin the new non-fatal warning: hits carry file + line +
term + original line; negated/closed contexts and the whitelist must not fire;
`--strict` warns but does not fail; the delivery-phase switch upgrades to fail.
"""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

mod_val = import_module("03_validate_kit")

BODY = "这是经过核实并亲口拍板的真实个人核心记录条目，用于测试验证完整性。" * 3


def _kit(tmp_path: pathlib.Path, marker_line: str | None = None) -> pathlib.Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (kit / fname).write_text(f"# {fname}\n\n{BODY}\n", encoding="utf-8")
    (kit / "AGENTS.md").write_text(
        (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    if marker_line is not None:
        (kit / "02-核心判断准则.md").write_text(
            f"# 02\n\n{BODY}\n{marker_line}\n", encoding="utf-8"
        )
    return kit


def _prose_msgs(msgs: list[str]) -> list[str]:
    return [m for m in msgs if m.startswith("UNCERTAIN_PROSE:")]


# --- Hit variants -----------------------------------------------------------


def test_prose_doubt_reported_with_file_line_term_and_original(tmp_path: pathlib.Path) -> None:
    line = "- 记不清当时到底有没有发出去，需要回原文核对"
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, line))
    assert ok, msgs
    hits = _prose_msgs(msgs)
    assert len(hits) == 1, hits
    assert hits[0].startswith("UNCERTAIN_PROSE: 02-核心判断准则.md:4 ")
    assert "命中“记不清”" in hits[0]
    assert "记不清当时到底有没有发出去" in hits[0]


def test_spaced_fullwidth_variant_is_normalized_before_match(tmp_path: pathlib.Path) -> None:
    # "待 核 实" with a full-width space: must still hit 待核实 after normalization.
    line = "- 这条线索待　核　实，先不写成结论"
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, line))
    assert ok, msgs
    hits = _prose_msgs(msgs)
    assert len(hits) == 1, hits
    assert "命中“待核实”" in hits[0]


def test_other_uncertainty_terms_hit(tmp_path: pathlib.Path) -> None:
    line = "- 可能记错了那次发布的时间，印象里大概是在去年启动的"
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, line))
    assert ok, msgs
    hits = _prose_msgs(msgs)
    assert hits, msgs
    assert any("命中“可能记错”" in h for h in hits)
    # One hit per line; the first matched term in list order is reported.
    assert len(hits) == 1


# --- Counterexamples: no false positives ------------------------------------


def test_negated_closed_context_is_not_reported(tmp_path: pathlib.Path) -> None:
    line = "- 不是不确定，所有条目都已核实通过，不存在遗留疑点"
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, line))
    assert ok, msgs
    assert _prose_msgs(msgs) == []


def test_clean_verified_fact_has_no_prose_hit(tmp_path: pathlib.Path) -> None:
    ok, msgs = mod_val.validate_kit(_kit(tmp_path))
    assert ok, msgs
    assert _prose_msgs(msgs) == []


def test_compound_term_uncertainty_degree_is_not_reported(tmp_path: pathlib.Path) -> None:
    # "不确定度" is a technical compound, not a doubt hedge.
    line = "- 保留不确定度词，绝不瞎编肯定的结论"
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, line))
    assert ok, msgs
    assert _prose_msgs(msgs) == []


def test_whitelist_exempts_a_line(tmp_path: pathlib.Path) -> None:
    line = "- 大概是这样写的（引用示例，本行可忽略）"
    ok, msgs = mod_val.validate_kit(
        _kit(tmp_path, line), uncertain_prose_whitelist=["引用示例"]
    )
    assert ok, msgs
    assert _prose_msgs(msgs) == []


# --- Strict / delivery switch behavior --------------------------------------


def test_strict_warns_but_does_not_fail_on_prose(tmp_path: pathlib.Path) -> None:
    line = "- 说不准当年到底先做的哪一个副业方向"
    ok, msgs = mod_val.validate_kit(_kit(tmp_path, line), strict=True)
    assert ok, msgs
    hits = _prose_msgs(msgs)
    assert len(hits) == 1, hits
    assert "命中“说不准”" in hits[0]
    assert any(m.startswith("WARN:") for m in msgs)


def test_fail_on_uncertain_prose_upgrades_warning_to_failure(tmp_path: pathlib.Path) -> None:
    line = "- 忘了细节，需要翻 Stage 3 记录再确认"
    ok, msgs = mod_val.validate_kit(
        _kit(tmp_path, line), fail_on_uncertain_prose=True
    )
    assert not ok
    assert any("UNCERTAIN_PROSE" in m for m in msgs)
