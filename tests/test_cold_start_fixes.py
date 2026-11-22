# -*- coding: utf-8 -*-
"""Regression tests for the 2026-11-22 cold-start audit (issues 01-04, 07)."""

from __future__ import annotations

import json
import pathlib
import sys
import zipfile
from importlib import import_module

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

mod_clean = import_module("01_clean_and_index")
mod_match = import_module("02_four_way_match")
mod_val = import_module("03_validate_kit")

FILLER = "这是经过核实并亲口拍板的真实个人核心记录条目，用于测试验证完整性。"


def _make_kit(tmp_path: pathlib.Path, extra_03: str = "") -> pathlib.Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    for fname in mod_val.REQUIRED_KIT_FILES:
        (kit / fname).write_text(f"# {fname}\n\n" + FILLER * 3, encoding="utf-8")
    (kit / "AGENTS.md").write_text((REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8")
    if extra_03:
        (kit / "03-硬规则与表达黑话.md").write_text(f"# 03\n\n{FILLER * 3}\n{extra_03}\n", encoding="utf-8")
    return kit


def _index(tmp_path: pathlib.Path, name: str, text: str) -> pathlib.Path:
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    (raw / name).write_text(text, encoding="utf-8")
    db = tmp_path / "idx.db"
    mod_clean.clean_and_index(raw, db)
    return db


# issue 01: ScriptCat-style exporter (## 🧑 User / ## 🤖 DeepSeek AI) must parse roles, date, fences.
def test_extract_scriptcat_export_roles_date_and_fences(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "sc.md"
    p.write_text(
        "# 预约小程序联调\n\n"
        "- **URL**: https://chat.deepseek.com/a/chat/s/abc\n"
        "- **Date**: 11/22/2026\n\n"
        "---\n\n"
        "## 🧑 User\n\n```text\n我这边卡在回调联调\n```\n\n"
        "---\n\n"
        "## 🤖 DeepSeek AI\n\n先确认签名串字段。\n\n"
        "---\n\n"
        "## 🧑 User\n\n```text\n我试过两次还是失败\n```\n",
        encoding="utf-8",
    )
    rows = mod_clean._extract_from_text(p)
    assert [r["role"] for r in rows] == ["user", "assistant", "user"]
    assert rows[0]["created_at"] == "2026-11-22"
    assert "```" not in rows[0]["content"]
    assert "预约小程序联调" not in rows[0]["content"]


# issue 02: GBK / UTF-16 must be decoded, never stored as U+FFFD mojibake.
def test_gbk_and_utf16_exports_are_decoded(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "gbk.md").write_bytes("## 2026-11-20 记录\nUser: 我说的是联调不是连掉\n".encode("gb18030"))
    (raw / "u16.md").write_bytes("## 2026-11-21 记录\nUser: 我指的是回调不是回掉\n".encode("utf-16"))
    db = tmp_path / "enc.db"
    stats = mod_clean.clean_and_index(raw, db)
    assert stats["decode_failed"] == 0
    import sqlite3

    content = "\n".join(r[0] for r in sqlite3.connect(db).execute("SELECT content FROM records"))
    assert "联调" in content and "回调" in content
    assert "\ufffd" not in content


# issue 03: "export all" zip must be extracted and indexed without manual steps.
def test_zip_export_is_extracted_and_indexed(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    with zipfile.ZipFile(raw / "all.zip", "w") as zf:
        zf.writestr("conv.md", "## 2026-11-20 记录\nUser: zip 里的验收标准\n")
    stats = mod_clean.clean_and_index(raw, tmp_path / "zip.db")
    assert stats["zip_extracted"] == 1
    assert stats["indexed"] >= 1


# issue 07: correction wording that is not one of the author's seeds must still become a candidate.
def test_user_correction_is_detected_without_seed_wording(tmp_path: pathlib.Path) -> None:
    db = _index(
        tmp_path,
        "dirac.md",
        "## Metadata\n- **Time:** 2026-10-15 21:30:00 +08:00\n\n## Conversation\n\n"
        "### 🧑‍💻 User\n我觉得这里还是不太像，你得先去测试对比\n\n"
        "### 🤖 Assistant\n抱歉，我重做。\n\n"
        "### 🧑‍💻 User\n我说了要先测试再写代码\n\n"
        "### 🤖 Assistant\n明白。\n",
    )
    report = mod_match.run_four_way_pipeline(db, ["验收"])
    assert "用户明确纠正或否定（规则）" in report["pattern_hits"]
    assert report["candidate_total"] >= 1


# issue 07: zero candidates must not be reported as FOUR_WAY_OK.
def test_zero_candidates_exits_nonzero(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    db = _index(
        tmp_path,
        "plain.md",
        "## Metadata\n- **Time:** 2026-11-20 10:00:00 +08:00\n\n## Conversation\n\n"
        "### 🧑‍💻 User\n今天天气挺好的，适合出门散步\n\n"
        "### 🤖 Assistant\n是的，适合散步。\n",
    )
    patterns = tmp_path / "p.json"
    patterns.write_text(json.dumps([{"kind": "method_principle", "title": "无关种子", "seeds": ["完全无关的种子句子"]}], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "02_four_way_match.py", "--db", str(db), "--out", str(tmp_path / "out.md"),
        "--keywords", "不存在的关键词", "--patterns", str(patterns),
    ])
    code = mod_match.main()
    out = capsys.readouterr().out
    assert code == 2
    assert "FOUR_WAY_NO_CANDIDATES" in out
    assert "FOUR_WAY_OK" not in out


# issue 04: an honest [待确认] marker must not fail --strict.
def test_strict_allows_pending_marker(tmp_path: pathlib.Path) -> None:
    kit = _make_kit(tmp_path)
    (kit / "04-正反例避坑账.md").write_text(
        f"# 04\n\n{FILLER * 3}\n[待确认] 尾款金额 ｜ 原文：「好像还有三千」 ｜ 出处：interview.md:12\n",
        encoding="utf-8",
    )
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs
    assert any("INFO" in m and "待确认" in m for m in msgs)


# issue 04: a rule that lists forbidden cliches must not itself be flagged.
def test_cliche_exemption_for_dont_use_phrase(tmp_path: pathlib.Path) -> None:
    kit = _make_kit(tmp_path, extra_03="不要用“打造全链路闭环生态”这类词。")
    ok, msgs = mod_val.validate_kit(kit, strict=True)
    assert ok, msgs


# issue 03: missing / wrong-schema DB must be a marker, not a raw traceback.
def test_missing_db_returns_marker(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", [
        "02_four_way_match.py", "--db", str(tmp_path / "missing.db"), "--out", str(tmp_path / "o.md"),
    ])
    assert mod_match.main() == 2
    out = capsys.readouterr().out
    assert "FOUR_WAY_DB_NOT_FOUND" in out
    assert "Traceback" not in out


def test_bad_schema_db_returns_marker(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import sqlite3

    bad = tmp_path / "bad.db"
    con = sqlite3.connect(bad)
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    monkeypatch.setattr(sys, "argv", [
        "02_four_way_match.py", "--db", str(bad), "--out", str(tmp_path / "o.md"),
    ])
    assert mod_match.main() == 2
    out = capsys.readouterr().out
    assert "FOUR_WAY_BAD_DB" in out
    assert "Traceback" not in out


# issue 07: seeds can come from the user's own kit instead of the author's wording.
def test_patterns_from_kit(tmp_path: pathlib.Path) -> None:
    kit = _make_kit(tmp_path)
    (kit / "02-核心判断准则.md").write_text(f"# 02\n\n- 先写测试再写代码，只有一次机会\n", encoding="utf-8")
    (kit / "04-正反例避坑账.md").write_text(f"# 04\n\n- 不要在没定验收标准前开工\n", encoding="utf-8")
    patterns = mod_match.patterns_from_kit(kit)
    seeds = [s for _, _, items in patterns for s in items]
    assert any("测试" in s for s in seeds)
    assert any("验收" in s for s in seeds)
