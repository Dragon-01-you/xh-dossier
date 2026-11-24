#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #88 / #89: interview answers are absorbed as A-level facts with traceable
source lines; interview outranks raw backfill; conflicts are marked, never
silently overwritten.
"""

import importlib
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

INTERVIEW = importlib.import_module("interview_source")
BOOTSTRAP = importlib.import_module("04_bootstrap_kit")

ANSWERS_MD = """# 6 个阶段访谈记录

## 汇总

- 称呼：芯火
- 身份 / 阶段：学生
- 当前项目：多个 Agent 的多人对话聚合，卡在测试
- 判断准则：1A（目标与真需求优先）/ 2C（内外双验收）/ 3B（单点卡 15 分钟换路线）
- 红线：原始资料可导出但需本人批准；未经本人同意不要删文件
- 正例：先对齐需求；AI 不懂主动提问
- 反例：输出听不懂的内容；过度依赖 AI 没学到东西
"""

ROUND_1_MD = """# 第 1 阶段

### 用户原话（逐条）
1. 角色定位：我希望你成为一个严谨的合伙人。
4. 操作规范：动手前先确认，review 一下；没有经过本人同意，不要删文件。
"""


def _write_interview(tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "interview"
    folder.mkdir()
    (folder / "answers.md").write_text(ANSWERS_MD, encoding="utf-8")
    (folder / "round-1.md").write_text(ROUND_1_MD, encoding="utf-8")
    return folder


def _db(tmp_path: pathlib.Path, extra_rows: list[tuple[str, str, str, str, str]] | None = None) -> pathlib.Path:
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    rows = [
        ("REC-0001", "20261101-100000-剪辑系统.md", "2026-11-01", "user",
         "我正在做 Agent 多人对话聚合系统，目前卡在测试环节，需要把每步产物留存下来。"),
        ("REC-0002", "20261101-100000-剪辑系统.md", "2026-11-01", "user",
         "判断原则是先对齐真实需求，再谈方法骨架，每一步都要能被本人复核。"),
        ("REC-0003", "20261102-100000-笔记.md", "2026-11-02", "user",
         "有效的做法是开工前先把需求对齐，AI 不懂的地方要主动反问本人。"),
    ]
    if extra_rows:
        rows += extra_rows
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                    [(a, b, c, d, e, "x", "", "stated") for a, b, c, d, e in rows])
    con.commit()
    con.close()
    return db


def test_parser_loads_slots_with_file_and_line(tmp_path: pathlib.Path) -> None:
    folder = _write_interview(tmp_path)
    bundle = INTERVIEW.load_interview(folder)
    assert not bundle.is_empty()

    by_name = {f.slot: f for f in bundle.facts}
    name = bundle.get("name")
    assert name is not None and name.text == "芯火"
    assert name.source_file == "answers.md" and name.source_line > 0

    identity = bundle.get("identity")
    assert identity is not None and identity.text == "学生"

    mainline = bundle.get("mainline")
    assert mainline is not None and "多人对话聚合" in mainline.text

    principles = bundle.by_slot("principle")
    codes = {f.code for f in principles}
    assert {"1A", "2C", "3B"} <= codes

    rules = bundle.by_slot("rule")
    rule_text = " ".join(f.text for f in rules)
    assert "不要删文件" in rule_text
    # Round-file rule extraction keeps original provenance.
    assert any(f.source_file == "round-1.md" for f in rules)

    # Every fact carries an original source line, not a fabricated one.
    for fact in bundle.facts:
        assert fact.source_file and fact.source_line >= 1
        assert fact.quote.strip()


def test_bootstrap_absorbs_interview_into_six_files(tmp_path: pathlib.Path) -> None:
    folder = _write_interview(tmp_path)
    db = _db(tmp_path)
    kit = tmp_path / "kit"
    res = BOOTSTRAP.build_kit(db, kit, interview=folder)

    assert res["interview_facts"] > 0
    assert res["validate_ok"], res["validate_messages"]

    joined = "\n".join(p.read_text(encoding="utf-8") for p in kit.rglob("*.md"))
    # The acceptance facts from answers.md must be visible in the kit.
    for token in ("芯火", "学生", "1A", "2C", "3B", "动手前先确认", "不要删文件"):
        assert token in joined, f"interview fact missing from kit: {token}"

    # Every interview bullet cites the in-kit digest line AND the original
    # file:line. A keyword hit without provenance is not accepted as absorption.
    digest = (kit / BOOTSTRAP.INTERVIEW_EVIDENCE_REL)
    assert digest.is_file(), "interview evidence digest was not copied into the kit"
    digest_lines = digest.read_text(encoding="utf-8").splitlines()

    bullets = [ln for ln in joined.splitlines() if "A级·访谈" in ln]
    assert bullets, "no A-level interview bullets were rendered"
    for bullet in bullets:
        m_digest = re.search(r"_evidence/interview-lines\.md:(\d+)", bullet)
        m_source = re.search(r"来源：(\S+?):(\d+)", bullet)
        assert m_digest, f"bullet lacks in-kit digest citation: {bullet}"
        assert m_source, f"bullet lacks original source citation: {bullet}"
        line_no = int(m_digest.group(1))
        assert 1 <= line_no <= len(digest_lines)
        digest_row = digest_lines[line_no - 1]
        assert m_source.group(1) in digest_row and m_source.group(2) in digest_row


def test_interview_outranks_raw_and_conflict_is_marked(tmp_path: pathlib.Path) -> None:
    folder = _write_interview(tmp_path)
    # A raw identity candidate that contradicts the interview ("学生").
    extra = [
        ("REC-0004", "20261103-100000-自由职业.md", "2026-11-03", "user",
         "我是自由职业者，正在做独立网页设计接单，平时自己接项目。"),
    ]
    db = _db(tmp_path, extra_rows=extra)
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit, interview=folder)

    identity_md = (kit / "01-身份与当前主线.md").read_text(encoding="utf-8")
    # Interview fact stays at the top and is not overwritten by the raw claim.
    assert "芯火" in identity_md and "学生" in identity_md
    # The disagreeing raw candidate carries an explicit pending conflict marker.
    conflict_lines = [ln for ln in identity_md.splitlines()
                      if "[待确认]" in ln and ln.startswith("- **候选")]
    assert conflict_lines, "conflicting raw candidate was not marked [待确认]"
    note = conflict_lines[0]
    assert "以访谈 A 级为准" in note
    assert "不得覆盖访谈记录" in note


def test_interview_principle_is_not_reported_as_empty(tmp_path: pathlib.Path) -> None:
    """A-level interview principles are sourced bullets; semantic audit must not
    mistake them for an empty 02 file just because they do not start with 候选."""
    folder = _write_interview(tmp_path)
    db = _db(tmp_path)
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit, interview=folder)

    findings = BOOTSTRAP.VALIDATOR.audit_semantics(kit)
    empty = [f for f in findings if f.code == "SEMANTIC_PRINCIPLE_EMPTY"]
    assert not empty, empty


def test_no_interview_keeps_baseline_behaviour(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    kit = tmp_path / "kit"
    res = BOOTSTRAP.build_kit(db, kit)
    assert res["interview_facts"] == 0
    assert res["validate_ok"], res["validate_messages"]
    joined = "\n".join(p.read_text(encoding="utf-8") for p in kit.rglob("*.md"))
    assert "A级·访谈" not in joined
