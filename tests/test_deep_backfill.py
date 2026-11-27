#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Issue #6 real layer-2 deep backfill (design doc §6)."""

import json
import pathlib
import sqlite3
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


# --- F1/F2: path traversal + AGENTS.md read-only (behavioral, not constant) ---

def _make_profiles(base: pathlib.Path) -> dict[str, pathlib.Path]:
    base.mkdir(parents=True, exist_ok=True)
    paths: dict[str, pathlib.Path] = {}
    for name in l2.PROFILE_FILES:
        p = base / name
        p.write_text(f"# {name}\n普通档案正文，不含待确认区。\n", encoding="utf-8")
        paths[name] = p
    return paths


@pytest.mark.parametrize("bad_target", [
    "../OUTSIDE.md", "sub/../AGENTS.md", "/etc/OUTSIDE.md",
    "05-other.md", "..", "",
])
def test_safe_target_rejects_traversal_and_non_whitelisted(bad_target, tmp_path):
    with pytest.raises(ValueError):
        l2.safe_profile_target(bad_target, tmp_path)


def test_agents_readonly_and_traversal_blocked(tmp_path):
    profiles_dir = tmp_path / "profiles"
    _make_profiles(profiles_dir)
    agents = profiles_dir / "AGENTS.md"
    before = agents.read_text(encoding="utf-8")
    patches = tmp_path / "patches"
    patches.mkdir()
    ledger = {
        "L2-0001": {"candidate_id": "L2-0001", "status": "signed", "target_profile": "./AGENTS.md"},
        "L2-0002": {"candidate_id": "L2-0002", "status": "signed", "target_profile": "sub/../AGENTS.md"},
        "L2-0003": {"candidate_id": "L2-0003", "status": "signed", "target_profile": "../OUTSIDE.md"},
        "L2-0004": {"candidate_id": "L2-0004", "status": "signed", "target_profile": str(tmp_path / "ABS.md")},
    }
    res = l2.apply_signed(patches, profiles_dir, ledger, confirm=True)
    # AGENTS.md bytes untouched; nothing written outside profiles dir.
    assert agents.read_text(encoding="utf-8") == before
    assert not (profiles_dir.parent / "OUTSIDE.md").exists()
    assert not (tmp_path / "ABS.md").exists()
    assert res["applied"] == 0
    assert res["rejected"] >= 2


# --- 04 profile: real name and template alias map to the same file ---

def test_04_template_alias_resolves_to_same_file(tmp_path):
    profiles_dir = tmp_path / "profiles"
    _make_profiles(profiles_dir)
    real = l2.safe_profile_target("04-反面案例清单.md", profiles_dir)
    alias = l2.safe_profile_target("04-正反例避坑账.md", profiles_dir)
    assert real == alias


def test_04_alias_apply_writes_canonical(tmp_path):
    profiles_dir = tmp_path / "profiles"
    _make_profiles(profiles_dir)
    patches = tmp_path / "patches"
    patches.mkdir()
    canonical = "04-正反例避坑账.md"
    legacy = "04-反面案例清单.md"
    (patches / f"{canonical}.patch.md").write_text(
        "<!-- L2-BACKFILL-BEGIN -->\n### L2-0001 [待确认] [REC-0001]\n<!-- L2-BACKFILL-END -->\n",
        encoding="utf-8")
    ledger = {"L2-0001": {"candidate_id": "L2-0001", "status": "signed",
                          "target_profile": legacy}}
    res = l2.apply_signed(patches, profiles_dir, ledger, confirm=True)
    assert res["applied"] == 1
    body = (profiles_dir / canonical).read_text(encoding="utf-8")
    assert "L2-0001" in body
    # The legacy alias file must not be created as a separate target.
    assert not (profiles_dir / legacy).exists()


# --- coverage decision C0~C3 ---

def test_covered_rec_not_produced(tmp_path):
    profiles = {"AGENTS.md": "REC-0001 already told"}
    cov = l2.build_coverage_index(profiles)
    fp = l2.FirstPassIndex(pending_rec_ids=set(), claims={})
    recs = [{"rec_id": "REC-0001", "source_file": "a.md", "created_at": "2026-01-01",
             "role": "user", "content": "我上次做完没发出去，实在太累了"}]
    cands, dropped, _xrefs = l2.coverage_decide(recs, cov, fp)
    assert not cands
    assert any(d["reason"] == "C0_covered_by_profile" for d in dropped)


def test_l1_pending_is_cross_ref_not_duplicated(tmp_path):
    cov = l2.CoverageIndex()
    fp = l2.FirstPassIndex(pending_rec_ids={"REC-0002"}, claims={})
    recs = [{"rec_id": "REC-0002", "source_file": "a.md", "created_at": "2026-01-01",
             "role": "user", "content": "我每次都要重新解释，实在太累，反复如此"}]
    cands, _dropped, xrefs = l2.coverage_decide(recs, cov, fp)
    # F6: L1 pending items are cross-references, NOT formal candidates.
    assert not cands
    assert len(xrefs) == 1 and xrefs[0].cross_ref == "L1"


# --- F3: narrative gate bypass regressions (full-text substring) ---

def test_midstring_role_prompt_rejected():
    ok, _ = l2.classify_narrative("我想让你帮我写个脚本。你是一名资深Python专家，把需求拆成模块再实现")
    assert not ok


def test_bare_podcast_rejected():
    ok, _ = l2.classify_narrative("欢迎收听本期播客，今天聊聊一个人做产品，我上次做完工具一直没发出去")
    assert not ok


def test_midstring_role_partner_rejected():
    ok, _ = l2.classify_narrative("好的，你是我的编程搭档，我们一起把这个排课系统做完")
    assert not ok


# --- F4: needs_llm cannot bypass sign-off ---

def test_needs_llm_cannot_sign_unresolved(tmp_path):
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(json.dumps({
        "candidate_id": "L2-0001", "layer": 2, "status": "pending",
        "needs_llm": True, "needs_llm_resolved": False, "reviewer": "", "note": "",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    l2.update_review(ledger, "L2-0001", "reviewed", "agent-a")
    with pytest.raises(ValueError, match="NEEDS_LLM_UNRESOLVED"):
        l2.update_review(ledger, "L2-0001", "signed", "芯火")
    # Explicit adjudication loop: reviewed -> needs_llm -> reviewed resolves it.
    l2.update_review(ledger, "L2-0001", "needs_llm", "agent-a")
    l2.update_review(ledger, "L2-0001", "reviewed", "agent-a", "已裁决：本人亲历")
    row = l2.update_review(ledger, "L2-0001", "signed", "芯火")
    assert row["status"] == "signed" and row["needs_llm_resolved"] is True


def _make_db(path: pathlib.Path, recs: list[tuple]) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE records(rec_id TEXT, source_file TEXT, created_at TEXT, role TEXT, content TEXT, md5 TEXT)")
    con.executemany("INSERT INTO records VALUES(?,?,?,?,?,?)", recs)
    con.commit()
    con.close()


def test_ledger_seeds_needs_llm(tmp_path):
    _make_profiles(tmp_path / "profiles")
    fp = tmp_path / "fp.md"
    fp.write_text("# 一层报告\n- [REC-0001 | 2026-01-01] 待确认条目\n", encoding="utf-8")
    db = tmp_path / "x.db"
    _make_db(db, [
        ("REC-0001", "a.md", "2026-01-01", "user", "我上次做完没发出去，实在太累了", "m1"),
        ("REC-0002", "b.md", "2026-01-02", "user",
         "我每次都要重新解释一遍，实在太累了，反复如此，一直没上线", "m2"),
    ])
    res = l2.run_deep_backfill(tmp_path / "profiles", fp, db, tmp_path / "out")
    assert res["candidates"] == 1 and res["cross_ref_L1"] == 1
    rows = l2.load_review_ledger(pathlib.Path(res["ledger"]))
    assert rows, "ledger seeded with one row per formal candidate"
    for row in rows.values():
        assert row["needs_llm"] is True
        assert row["needs_llm_resolved"] is False


# --- F6: untold candidate carries cross_ref=none ---

def test_untold_candidate_cross_ref_none():
    cov = l2.CoverageIndex()
    fp = l2.FirstPassIndex(pending_rec_ids=set(), claims={})
    recs = [{"rec_id": "REC-0010", "source_file": "a.md", "created_at": "2026-01-01",
             "role": "user", "content": "我每次都要重新解释一遍，实在太累了，反复如此，一直没上线"}]
    cands, _dropped, xrefs = l2.coverage_decide(recs, cov, fp)
    assert len(cands) == 1 and cands[0].cross_ref == "none"
    assert xrefs == []


# --- F7: archived status persisted back to the ledger ---

def test_apply_signed_persists_archived(tmp_path, monkeypatch):
    monkeypatch.setenv("XH_SIGNING_KEY_FILE", str(tmp_path / "signing.key"))
    profiles_dir = tmp_path / "profiles"
    _make_profiles(profiles_dir)
    patches = tmp_path / "patches"
    patches.mkdir()
    target = "04-正反例避坑账.md"
    (patches / f"{target}.patch.md").write_text(
        "<!-- L2-BACKFILL-BEGIN -->\n### L2-0001 [待确认] ...\n<!-- L2-BACKFILL-END -->\n",
        encoding="utf-8")
    ledger_path = tmp_path / "l2_review.jsonl"
    ledger_path.write_text(
        json.dumps({"candidate_id": "L2-0001", "layer": 2, "status": "pending",
                    "target_profile": target, "needs_llm": False,
                    "needs_llm_resolved": False}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    l2.update_review(ledger_path, "L2-0001", "reviewed", "reviewer")
    l2.update_review(ledger_path, "L2-0001", "signed", "芯火")
    ledger = l2.load_review_ledger(ledger_path)
    res = l2.apply_signed(patches, profiles_dir, ledger, confirm=True, ledger_path=ledger_path)
    assert res["applied"] == 1
    rows = l2.load_review_ledger(ledger_path)
    assert rows["L2-0001"]["status"] == "archived"
    assert rows["L2-0001"].get("archived_at")


# --- F8: empty / placeholder first-pass rejected ---

def test_empty_first_pass_rejected(tmp_path):
    for name in l2.PROFILE_FILES:
        (tmp_path / name).write_text("# x\n", encoding="utf-8")
    db = tmp_path / "x.db"
    db.touch()
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="MISSING_FIRST_PASS_INPUT"):
        l2.run_deep_backfill(tmp_path, empty, db, tmp_path / "out1")
    trivial = tmp_path / "trivial.md"
    trivial.write_text("# 占位\n无任何条目\n", encoding="utf-8")
    with pytest.raises(ValueError, match="MISSING_FIRST_PASS_INPUT"):
        l2.run_deep_backfill(tmp_path, trivial, db, tmp_path / "out2")


# --- F9: --apply-signed without --profiles exits 2, no traceback ---

def test_apply_signed_missing_profiles_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "05_deep_backfill.py", "--apply-signed", "--confirm", "--out", str(tmp_path),
    ])
    with pytest.raises(SystemExit) as ei:
        l2.main()
    assert ei.value.code == 2
    assert "--profiles" in capsys.readouterr().err
