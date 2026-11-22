# -*- coding: utf-8 -*-
"""Comprehensive unit and end-to-end tests for the AI Onboarding Kit scripts."""

from __future__ import annotations

import json
import pathlib
import sys
from importlib import import_module

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

mod_wizard = import_module("00_export_wizard")
mod_clean = import_module("01_clean_and_index")
mod_match = import_module("02_four_way_match")
mod_val = import_module("03_validate_kit")


def test_export_wizard_requires_consent_and_supports_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    opened: list[str] = []
    # Declining consent must perform zero external browser/download side effects
    res_declined = mod_wizard.run_wizard(
        browser="edge",
        auto_yes=False,
        dry_run=False,
        input_fn=lambda _: "n",
        open_url_fn=lambda u: opened.append(u) or True,
    )
    assert res_declined["consented"] is False
    assert opened == []

    # With consent + dry-run, official ScriptCat link and MV3 switch steps print cleanly
    res_dry = mod_wizard.run_wizard(
        browser="edge",
        auto_yes=True,
        dry_run=True,
        open_url_fn=lambda u: opened.append(u) or True,
    )
    out = capsys.readouterr().out
    assert res_dry["consented"] is True
    assert opened == []
    assert "scriptcat.org" in out
    assert "允许运行用户脚本" in out


def test_clean_dedup_and_keyword_search(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "cold.db"
    stats = mod_clean.clean_and_index(REPO_ROOT / "examples" / "sample_raw", db_path)

    assert stats["total_raw"] >= 8
    assert stats["dedup_skipped"] >= 1
    assert stats["indexed"] == stats["total_raw"] - stats["dedup_skipped"]

    # FTS5 trigram search (>= 3 chars)
    long_hits = mod_clean.search_keyword(db_path, "验收标准")
    assert len(long_hits) >= 2

    # Escaped SQL LIKE fallback (< 3 chars): "%" must match only literal "10%", not act as wildcard for all rows
    short_hits = mod_clean.search_keyword(db_path, "记错")
    assert len(short_hits) >= 1
    assert any("REC-" in h["rec_id"] for h in short_hits)
    pct_hits = mod_clean.search_keyword(db_path, "%")
    assert len(pct_hits) == 1 and "10%" in pct_hits[0]["content"]
    assert mod_clean.search_keyword(db_path, "%%") == []
    assert mod_clean.search_keyword(db_path, "_") == []


def test_clean_supports_jsonl_chatgpt_mapping_and_skips_empty_md_headers(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()

    # Local CLI .jsonl + broken line tolerance
    (raw / "cli.jsonl").write_text(
        json.dumps({"role": "user", "content": "jsonl里的第一条验收记录", "timestamp": "2026-11-01"}, ensure_ascii=False)
        + "\n{broken json}\n",
        encoding="utf-8",
    )

    # ChatGPT official `mapping` node export with list content parts
    (raw / "chatgpt.json").write_text(
        json.dumps(
            [
                {
                    "created_at": "2026-11-02",
                    "mapping": {
                        "n1": {
                            "message": {
                                "author": {"role": "user"},
                                "content": {"parts": ["ChatGPT导出树里的结构化提问"]},
                            }
                        }
                    },
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Markdown with empty heading-only section and multi-turn conversation
    (raw / "turns.md").write_text(
        "## 空标题不入库\n\n## 2026-11-03 真实双轮对话\nUser: 提问第一句需要核查\nAssistant: 回答第二句已确认",
        encoding="utf-8",
    )

    db_path = tmp_path / "mix.db"
    stats = mod_clean.clean_and_index(raw, db_path)
    assert stats["indexed"] == 4
    assert mod_clean.search_keyword(db_path, "空标题不入库") == []
    assert len(mod_clean.search_keyword(db_path, "jsonl")) == 1
    assert len(mod_clean.search_keyword(db_path, "ChatGPT导出树")) == 1


def test_missing_db_raises_without_creating_empty_file(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(FileNotFoundError):
        mod_clean.search_keyword(missing, "验收")
    with pytest.raises(FileNotFoundError):
        mod_match.run_four_way_pipeline(missing, ["验收"])
    assert not missing.exists()


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

    ok_method_neg, _ = mod_match.apply_guardrails("先别直接定死方案，先拿小样本验一遍", "method_principle")
    assert not ok_method_neg


def test_end_to_end_four_way_pipeline(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "demo.db"
    out_md = tmp_path / "backfill_candidates.md"
    mod_clean.clean_and_index(REPO_ROOT / "examples" / "sample_raw", db_path)

    report = mod_match.run_four_way_pipeline(db_path, ["记错", "验收"])
    md = mod_match.render_backfill_markdown(report)
    out_md.write_text(md, encoding="utf-8")

    assert report["records"] >= 7
    assert "Way 1" in md and "Way 3" in md and "Way 4" in md
    assert "跨越" in md
    assert "[已拦截" in md
    assert "[待确认]" in md


def test_validate_kit_templates_placeholders_and_pii(tmp_path: pathlib.Path) -> None:
    ok_non_strict, _ = mod_val.validate_kit(REPO_ROOT / "templates", strict=False)
    assert ok_non_strict

    ok_strict_tpl, msgs_tpl = mod_val.validate_kit(REPO_ROOT / "templates", strict=True)
    assert not ok_strict_tpl
    assert sum("UNFILLED placeholders" in m for m in msgs_tpl) == 5

    # Verify non-<填写...> placeholder variants are also caught in --strict mode
    custom_kit = tmp_path / "half_done"
    custom_kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (custom_kit / fname).write_text(f"# {fname}\n\n" + "正文占位样例" * 20, encoding="utf-8")
    (custom_kit / "01-身份与当前主线.md").write_text(
        "# 01\n\n" + "稳定事实内容够长检查通过。" * 6 + "\n- <一句话写清你的底层动机>", encoding="utf-8"
    )
    ok_half, msgs_half = mod_val.validate_kit(custom_kit, strict=True)
    assert not ok_half
    assert any("UNFILLED" in m for m in msgs_half)

    # Complete clean user kit (keeping template AGENTS.md rule mentioning `[待确认]`) passes strict mode
    clean_kit = tmp_path / "clean_kit"
    clean_kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (clean_kit / fname).write_text(f"# {fname}\n\n" + "这是经过核实并亲口拍板的真实个人核心记录条目，用于测试验证完整性。" * 3, encoding="utf-8")
    (clean_kit / "AGENTS.md").write_text((REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8")
    ok_clean, msgs_clean = mod_val.validate_kit(clean_kit, strict=True)
    assert ok_clean, msgs_clean

    ok_forbidden, msgs_forbidden = mod_val.validate_kit(clean_kit, strict=True, forbidden_terms=["真实个人核心记录"])
    assert not ok_forbidden
    assert any("FORBIDDEN_PII_TERM" in m for m in msgs_forbidden)

    (clean_kit / "00-总入口索引.md").write_text("# 00\n\n" + "正文记录" * 30 + "\n路径: C:\\Users\\Alice\\secret", encoding="utf-8")
    ok_leak, msgs_leak = mod_val.validate_kit(clean_kit, strict=True)
    assert not ok_leak
    assert any("PII_OR_SECRET_RISK" in m for m in msgs_leak)


def test_cli_missing_raw_dir_fails_with_actionable_message(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "missing.db"
    monkeypatch.setattr(
        sys,
        "argv",
        ["01_clean_and_index.py", "--raw", str(tmp_path / "does-not-exist"), "--db", str(db_path)],
    )

    code = mod_clean.main()
    out = capsys.readouterr().out

    assert code == 2
    assert "RAW_DIR_NOT_FOUND" in out
    assert "docs/02-multi-platform-export.md" in out
    assert "Traceback" not in out
    assert not db_path.exists()


def test_cli_empty_raw_dir_does_not_report_green_success(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_dir = tmp_path / "empty_raw"
    raw_dir.mkdir()
    db_path = tmp_path / "empty.db"
    monkeypatch.setattr(
        sys,
        "argv",
        ["01_clean_and_index.py", "--raw", str(raw_dir), "--db", str(db_path)],
    )

    code = mod_clean.main()
    out = capsys.readouterr().out

    assert code == 2
    assert "INDEX_EMPTY" in out
    assert "INDEX_OK" not in out
    assert "不要把 indexed=0 当成成功" in out


def test_cli_empty_database_does_not_write_fake_backfill_report(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_dir = tmp_path / "empty_raw"
    raw_dir.mkdir()
    db_path = tmp_path / "empty.db"
    mod_clean.clean_and_index(raw_dir, db_path)
    out_path = tmp_path / "backfill.md"
    monkeypatch.setattr(
        sys,
        "argv",
        ["02_four_way_match.py", "--db", str(db_path), "--out", str(out_path)],
    )

    code = mod_match.main()
    out = capsys.readouterr().out

    assert code == 2
    assert "FOUR_WAY_EMPTY" in out
    assert not out_path.exists()


def test_wizard_cli_returns_nonzero_when_consent_is_declined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod_wizard, "run_wizard", lambda **_: {"consented": False})
    monkeypatch.setattr(sys, "argv", ["00_export_wizard.py", "--browser", "edge", "--yes"])

    assert mod_wizard.main() == 1


def test_wizard_cli_returns_zero_after_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod_wizard, "run_wizard", lambda **_: {"consented": True})
    monkeypatch.setattr(sys, "argv", ["00_export_wizard.py", "--browser", "edge", "--yes"])

    assert mod_wizard.main() == 0
