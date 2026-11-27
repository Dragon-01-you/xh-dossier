#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for the v0.2.0-rc.5 TeleAgent report (P1/P2/P3/P7/P9/P12/P13/P15/P17/P18)."""

import argparse
import importlib
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

VALIDATOR = importlib.import_module("03_validate_kit")
BOOTSTRAP = importlib.import_module("04_bootstrap_kit")
INTERVIEW = importlib.import_module("interview_source")
BLIND = importlib.import_module("blind_test")
L2 = importlib.import_module("05_deep_backfill")
XH = importlib.import_module("xh")
CLEAN = importlib.import_module("01_clean_and_index")
EXPORT_GATE = importlib.import_module("10_export_gate")
FINALIZE = importlib.import_module("11_finalize_download")

ANSWERS_MD = """# 汇总

- 称呼：芯火
- 身份 / 阶段：学生
- 当前项目：多个 Agent 的多人对话聚合，卡在测试
- 判断准则：1A（目标与真需求优先）/ 2C（内外双验收）/ 3B（单点卡 15 分钟换路线）
- 红线：原始资料可导出但需本人批准；未经本人同意不要删文件
- 正例：先对齐需求；AI 不懂主动提问
- 反例：输出听不懂的内容；过度依赖 AI 没学到东西
"""

ROWS = [
    ("REC-0001", "a.md", "2026-11-01", "user",
     "我正在做 Agent 多人对话聚合系统，目前卡在测试环节，需要把每步产物留存下来。"),
    ("REC-0002", "a.md", "2026-11-01", "user",
     "判断原则是先对齐真实需求，再谈方法骨架，每一步都要能被本人复核。"),
    ("REC-0003", "b.md", "2026-11-02", "user",
     "有效的做法是开工前先把需求对齐，AI 不懂的地方要主动反问本人。"),
]


def _kit(tmp_path: pathlib.Path) -> pathlib.Path:
    interview = tmp_path / "interview"
    interview.mkdir()
    (interview / "answers.md").write_text(ANSWERS_MD, encoding="utf-8")
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    con.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                    [(a, b, c, d, e, "x", "", "stated") for a, b, c, d, e in ROWS])
    con.commit()
    con.close()
    kit = tmp_path / "kit"
    BOOTSTRAP.build_kit(db, kit, interview=interview)
    return kit


def test_p1_interview_citation_not_checked_against_raw(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    # A real raw export that does NOT contain the interview answer. Old code
    # failed every A-level bullet here; new code only checks the in-kit digest.
    raw = tmp_path / "work" / "raw"
    raw.mkdir(parents=True)
    (raw / "unrelated.md").write_text("这是一段与访谈无关的聊天记录。", encoding="utf-8")
    card = VALIDATOR.score_kit(kit, raw_root=raw)
    assert card["metrics"]["citation_accuracy"]["value"] == 1.0, card
    assert card["overall_passed"], card


def test_p2_build_passes_explicit_raw_root(tmp_path: pathlib.Path, monkeypatch) -> None:
    raw = tmp_path / "work" / "raw"
    raw.mkdir(parents=True)
    (raw / "chat.md").write_text("原件", encoding="utf-8")
    db = tmp_path / "work" / "unified_index.db"
    kit = tmp_path / "work" / "kit"
    kit.mkdir()
    l2 = tmp_path / "work" / "layer2"
    report = tmp_path / "work" / "backfill_candidates.md"
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(XH, "_run", fake_run)
    monkeypatch.setattr(XH, "_write_review_status", lambda *a, **k: None)
    args = argparse.Namespace(raw=str(raw), db=str(db), kit=str(kit), l2=str(l2),
                              report=str(report), interview=str(tmp_path / "interview"),
                              no_interview=False, skip_retrieval=True, no_l2_apply=True,
                              enforce_score=False, query="记错", apply_unsigned=True,
                              kit_next=None)
    assert XH.build(args) == 0
    validate_cmd = next(c for c in calls if any("03_validate_kit.py" in arg for arg in c))
    assert "--raw-root" in validate_cmd
    assert str(raw) in validate_cmd


def test_p12_auto_detects_work_interview(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "work" / "raw"
    raw.mkdir(parents=True)
    interview = tmp_path / "work" / "interview"
    interview.mkdir()
    (interview / "answers.md").write_text(ANSWERS_MD, encoding="utf-8")
    assert XH._detect_interview_dir(raw, tmp_path / "work" / "kit") == interview


def test_p3_p9_p16_interview_formats_and_empty_values(tmp_path: pathlib.Path) -> None:
    answers = tmp_path / "answers.md"
    answers.write_text(
        "# 访谈\n\n"
        "- 正反例滚动账：本阶段无\n"
        "- 身份阶段：在职（数字编号，应吸收）\n"
        "- 判断准则：先对齐需求再动手\n"
        "| 称呼 | 芯火 |\n"
        "**红线**：未经本人同意不要删文件\n"
        "问：当前项目是什么？\n"
        "答：多个 Agent 的多人对话聚合，卡在测试\n"
        "我的反例是：输出听不懂的内容\n",
        encoding="utf-8",
    )
    bundle = INTERVIEW.load_interview(answers)
    assert not bundle.by_slot("negative") or all(
        "本阶段无" not in f.text for f in bundle.by_slot("negative")
    )
    # "正反例滚动账" must not be routed to negative through substring "反例".
    assert all("滚动账" not in f.text for f in bundle.facts)
    name = bundle.get("name")
    assert name and name.text == "芯火", [f.__dict__ for f in bundle.facts]
    identity = bundle.get("identity")
    assert identity and "数字编号" not in identity.text, identity
    assert identity.text.startswith("在职")
    assert bundle.get("rule") and "不要删文件" in bundle.get("rule").text
    assert bundle.get("mainline") and "多人对话聚合" in bundle.get("mainline").text
    assert bundle.get("negative") and "输出听不懂" in bundle.get("negative").text


def test_p13_score_same_sheet_preserves_answers(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    kit = _kit(tmp_path)
    out = tmp_path / "blind"
    BLIND.build_blind_package(kit, out)
    expected = json.loads((out / ".expected.json").read_text(encoding="utf-8"))
    sheet = out / "盲测三问.md"
    filled = (
        "## Q1 当前主线\n"
        f"- 回答：{expected['mainline']['bullets'][0]}\n\n"
        "## Q2 三条判断\n"
        + "".join(f"- 回答：{b}\n" for b in expected["principle"]["bullets"][:3])
        + "\n## Q3 硬规则\n"
        + "".join(f"- 回答：{b}\n" for b in expected["rule"]["bullets"][:1])
    )
    sheet.write_text(filled, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "blind_test.py", "--kit", str(kit), "--out", str(out), "--score", str(sheet),
    ])
    assert BLIND.main() == 0
    assert "BLIND_PASS" in capsys.readouterr().out
    # The answer sheet must not be reset to a blank template.
    assert "回答：" in sheet.read_text(encoding="utf-8")


def test_p15_tampered_signed_ledger_is_rejected(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setenv("XH_SIGNING_KEY_FILE", str(tmp_path / "signing.key"))
    L2.init_signing_key()
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for name in ("00-总入口索引.md", "01-身份与当前主线.md", "02-核心判断准则.md",
                 "03-硬规则与表达黑话.md", "04-正反例避坑账.md"):
        (profiles / name).write_text("# x\n", encoding="utf-8")
    patches = tmp_path / "patches"
    patches.mkdir()
    (patches / "03-硬规则与表达黑话.md.patch.md").write_text(
        "<!-- L2-BACKFILL-BEGIN -->\n### L2-0001 [待确认]\n<!-- L2-BACKFILL-END -->\n",
        encoding="utf-8")
    ledger = tmp_path / "l2_review.jsonl"
    # Exactly the report's exploit: hand-edit pending -> signed, no signature.
    ledger.write_text(json.dumps({
        "candidate_id": "L2-0001", "layer": 2, "status": "signed",
        "reviewer": "芯火", "target_profile": "03-硬规则与表达黑话.md",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    res = L2.apply_signed(patches, profiles, L2.load_review_ledger(ledger),
                          confirm=True, ledger_path=ledger)
    assert res["applied"] == 0
    assert res["reason"].startswith("AUDIT_") or res["reason"].startswith("SIGNATURE_")


def test_p7_export_gate_distinguishes_missing_dir(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    missing = tmp_path / "no-such-raw"
    monkeypatch.setattr(sys, "argv", ["10_export_gate.py", "--raw", str(missing)])
    assert EXPORT_GATE.main() == 2
    out = capsys.readouterr().out
    assert "EXPORT_DIR_MISSING" in out
    assert "EXPORT_BUTTON_MISSING" not in out


def test_p17_finalize_none_is_normal(tmp_path: pathlib.Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["11_finalize_download.py", "--source-dir", str(tmp_path)])
    assert FINALIZE.main() == 0
    assert "FINALIZE_NONE" in capsys.readouterr().out


def test_p18_clean_text_removes_ui_timestamps() -> None:
    raw = "00:00｜08:04\n今天 12:28\n真正的回答\n\n\n\n下一段"
    cleaned = CLEAN.clean_text(raw)
    assert "00:00" not in cleaned and "08:04" not in cleaned
    assert "今天 12:28" not in cleaned
    assert "真正的回答" in cleaned


def test_p4_principle_sentence_not_routed_to_hard_rule() -> None:
    recs = [{"rec_id": "REC-0001", "source_file": "chat.md", "created_at": "2026-11-01",
              "role": "user", "content": "卡在改细节没上线的时候必须有人当场喊停我。"}]
    cands = L2.broad_candidates(recs, L2.CoverageIndex())
    assert cands
    assert cands[0].signal == "complaint"
    assert cands[0].target_profile == "02-核心判断准则.md"
