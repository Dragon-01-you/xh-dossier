#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #132: Graph denoising (user-only, no quote fragments, verified proposal import,
conflict export) + L3 reflection minimum programmatic gate contract."""

from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

GRAPH = importlib.import_module("06_graph_index")


def _make_db(
    tmp_path: pathlib.Path,
    records: list[tuple[str, str, str, str, str]],
) -> pathlib.Path:
    """records: list of (rec_id, source_file, created_at, role, content)."""
    db = tmp_path / "graph_l3.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records ("
        "rec_id TEXT PRIMARY KEY, source_file TEXT NOT NULL, created_at TEXT NOT NULL, "
        "role TEXT NOT NULL, content TEXT NOT NULL, md5 TEXT NOT NULL UNIQUE, "
        "event_date TEXT, date_kind TEXT)"
    )
    for rec_id, src, date, role, content in records:
        digest = hashlib.md5(f"{rec_id}:{content}".encode("utf-8")).hexdigest()
        con.execute(
            "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rec_id, src, date, role, content, digest, date, "stated"),
        )
    con.commit()
    con.close()
    return db


def test_graph_excludes_assistant_edges_and_drops_quoted_lyric_fragments(
    tmp_path: pathlib.Path,
) -> None:
    db = _make_db(
        tmp_path,
        [
            ("REC-0001", "s1.md", "2026-10-01", "assistant",
             "我学习 Docker 容器编排，我也使用 Kubernetes，还喜欢「左肩」和“喵——”。"),
            ("REC-0002", "s1.md", "2026-10-02", "user",
             "我学习 Python 自动化；刚才听歌听到“左肩”“爱你”“嗯——”“喵——”这些歌词。"),
        ],
    )
    stats = GRAPH.build_graph(db, lexicon=["Python"], rebuild=True)
    assert stats["edges"] >= 1

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    asst_edges = con.execute(
        "SELECT r.* FROM relations r JOIN records rec ON r.rec_id = rec.rec_id "
        "WHERE lower(rec.role) != 'user'"
    ).fetchall()
    ent_names = {r["canonical_name"] for r in con.execute("SELECT canonical_name FROM entities")}
    con.close()

    assert len(asst_edges) == 0, f"assistant edges leaked into graph: {[dict(r) for r in asst_edges]}"
    for noise in ("左肩", "爱你", "嗯——", "喵——", "Docker", "Kubernetes"):
        assert noise not in ent_names, f"noise entity should not exist: {noise}"
    assert "Python" in ent_names


def test_verified_structured_proposal_import_and_bitemporal_conflict_export(
    tmp_path: pathlib.Path,
) -> None:
    db = _make_db(
        tmp_path,
        [
            ("REC-0001", "s1.md", "2026-09-01", "user",
             "我现在主要用 Notion 来整理每日笔记和项目清单。"),
            ("REC-0002", "s2.md", "2026-11-10", "user",
             "我已经彻底放弃 Notion 了，全部迁移到本地 Obsidian 知识库。"),
            ("REC-0003", "s2.md", "2026-11-10", "assistant",
             "好的，我可以帮你把 Notion 导出迁移到 Obsidian。"),
        ],
    )
    GRAPH.build_graph(db, rebuild=True)

    proposals = [
        # Valid edge 1 (earlier)
        {
            "subject": "我（本人）",
            "relation": "USES",
            "object": "Notion",
            "rec_id": "REC-0001",
            "quote": "主要用 Notion 来整理每日笔记",
            "valid_from": "2026-09-01",
        },
        # Valid conflicting edge 2 (later opposite action on same object)
        {
            "subject": "我（本人）",
            "relation": "ABANDONED",
            "object": "Notion",
            "rec_id": "REC-0002",
            "quote": "已经彻底放弃 Notion 了",
            "valid_from": "2026-11-10",
        },
        # Fabricated rec_id -> MUST REJECT
        {
            "subject": "我（本人）",
            "relation": "USES",
            "object": "FakeDB",
            "rec_id": "REC-9999",
            "quote": "我使用 FakeDB",
            "valid_from": "2026-11-11",
        },
        # Tampered quote -> MUST REJECT
        {
            "subject": "我（本人）",
            "relation": "USES",
            "object": "Neo4j",
            "rec_id": "REC-0002",
            "quote": "我每天都在用 Neo4j 图数据库",
            "valid_from": "2026-11-11",
        },
        # Assistant record -> MUST REJECT
        {
            "subject": "我（本人）",
            "relation": "USES",
            "object": "Obsidian",
            "rec_id": "REC-0003",
            "quote": "帮你把 Notion 导出迁移到 Obsidian",
            "valid_from": "2026-11-10",
        },
    ]
    prop_file = tmp_path / "proposals.jsonl"
    prop_file.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in proposals) + "\n",
        encoding="utf-8",
    )

    res = GRAPH.import_verified_proposals(db, prop_file)
    assert res["accepted"] == 2, res
    assert res["rejected"] == 3, res
    reasons = {r["reason"] for r in res["rejections"]}
    assert "rec_id_not_found" in reasons
    assert "quote_mismatch" in reasons
    assert "non_user_record" in reasons

    # Bitemporal preservation: old USES edge closed (t_invalid=1, valid_to=2026-11-10), NOT deleted.
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    notion_edges = [dict(r) for r in con.execute("SELECT * FROM relations WHERE object='Notion' ORDER BY valid_from")]
    con.close()
    assert len(notion_edges) == 2, notion_edges
    old_e, new_e = notion_edges[0], notion_edges[1]
    assert old_e["relation"] == "USES" and old_e["t_invalid"] == 1
    assert old_e["valid_to"] == "2026-11-10"
    assert old_e["superseded_by"] == new_e["rel_id"]
    assert new_e["relation"] == "ABANDONED" and new_e["t_invalid"] == 0

    # Conflict export includes both sides' rec_id and original text excerpts.
    conflicts = GRAPH.export_conflicts(db)
    assert len(conflicts) >= 1
    md = GRAPH.render_conflicts_markdown(conflicts)
    assert "REC-0001" in md and "REC-0002" in md
    assert "主要用 Notion" in md and "彻底放弃 Notion" in md


def test_l3_reflection_gate_enforces_all_four_mechanical_rules(tmp_path: pathlib.Path) -> None:
    gate = importlib.import_module("12_l3_reflection_gate")
    db = _make_db(
        tmp_path,
        [
            ("REC-0001", "session_a.md", "2026-09-10", "user",
             "上次把静态小工具一直微调样式拖了六天没发布，错过活动时间，后来改成到点先发最小版本。"),
            ("REC-0002", "session_a.md", "2026-09-10", "user",
             "当天晚上复盘发现停在百分之八十不交付等于零，必须定死发布时间盒。"),
            ("REC-0003", "session_b.md", "2026-11-05", "user",
             "这次写自动化脚本又差点陷入继续优化细节不上线，我强制自己先交第一版拿真人反馈再改。"),
            ("REC-0004", "session_c.md", "2026-11-18", "user",
             "例外情况是涉及主库数据删除迁移时，宁可多花两天先建隔离镜像测试，不能仓促上线。"),
        ],
    )

    # 1. Single-evidence observation -> MUST FAIL G1
    r_single = gate.validate_observation(
        db,
        {
            "observation_id": "OBS-01",
            "statement": "面对交付焦虑时，先设定时间盒发布最小可用版再按反馈迭代。",
            "evidence": [{"rec_id": "REC-0001", "quote": "一直微调样式拖了六天没发布"}],
            "counterexamples": [],
            "evolution": "2026-09 初次记录",
        },
    )
    assert not r_single["passed"]
    assert "G1_MULTI_EVIDENCE" in r_single["failed_gates"]

    # 2. Same-date + same-session 2-evidence -> MUST FAIL G1
    r_same_day = gate.validate_observation(
        db,
        {
            "observation_id": "OBS-02",
            "statement": "面对交付焦虑时，先设定时间盒发布最小可用版再按反馈迭代。",
            "evidence": [
                {"rec_id": "REC-0001", "quote": "一直微调样式拖了六天没发布"},
                {"rec_id": "REC-0002", "quote": "停在百分之八十不交付等于零"},
            ],
            "counterexamples": [],
            "evolution": "同日两段复盘",
        },
    )
    assert not r_same_day["passed"]
    assert "G1_MULTI_EVIDENCE" in r_same_day["failed_gates"]

    # 3. Near-verbatim paraphrase of single L2 record -> MUST FAIL G2
    r_paraphrase = gate.validate_observation(
        db,
        {
            "observation_id": "OBS-03",
            "statement": "上次把静态小工具一直微调样式拖了六天没发布，错过活动时间，后来改成到点先发最小版本。",
            "evidence": [
                {"rec_id": "REC-0001", "quote": "上次把静态小工具一直微调样式拖了六天没发布，错过活动时间，后来改成到点先发最小版本。"},
                {"rec_id": "REC-0003", "quote": "我强制自己先交第一版拿真人反馈再改"},
            ],
            "counterexamples": [],
            "evolution": "2026-09 到 2026-11",
        },
    )
    assert not r_paraphrase["passed"]
    assert "G2_L2_PARAPHRASE" in r_paraphrase["failed_gates"]

    # 4. Missing evolution / counterexample slot -> MUST FAIL G3
    r_no_evo = gate.validate_observation(
        db,
        {
            "observation_id": "OBS-04",
            "statement": "在多轮工程实践里形成了先用时间盒发最小可用版收集真实反馈的跨期习惯。",
            "evidence": [
                {"rec_id": "REC-0001", "quote": "一直微调样式拖了六天没发布"},
                {"rec_id": "REC-0003", "quote": "强制自己先交第一版拿真人反馈再改"},
            ],
            "evolution": "",
        },
    )
    assert not r_no_evo["passed"]
    assert "G3_COUNTEREXAMPLE_AND_EVOLUTION" in r_no_evo["failed_gates"]

    # 5. Valid cross-date, cross-session, non-paraphrase observation with verified counterexample -> PASSES
    valid_obs = {
        "observation_id": "OBS-05",
        "statement": "在多轮个人交付中，倾向以刚性时间盒推动先发布最简可用版并收集外部反馈，而非追求首版完美。",
        "evidence": [
            {"rec_id": "REC-0001", "quote": "拖了六天没发布，错过活动时间，后来改成到点先发最小版本"},
            {"rec_id": "REC-0003", "quote": "强制自己先交第一版拿真人反馈再改"},
        ],
        "counterexamples": [
            {"rec_id": "REC-0004", "quote": "涉及主库数据删除迁移时，宁可多花两天先建隔离镜像测试，不能仓促上线"}
        ],
        "evolution": "2026-09 首次因拖延踩坑建立时间盒，2026-11 在脚本交付中复现并在数据安全场景补充例外边界。",
    }
    r_ok = gate.validate_observation(db, valid_obs)
    assert r_ok["passed"], r_ok

    # 6. Gate 4: promotion without personal sign-off is mechanically blocked and touches NO kit file.
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    f02 = kit_dir / "02-核心判断准则.md"
    f02.write_text("# 02-核心判断准则\n\n原始内容不可被未签字 L3 改写。\n", encoding="utf-8")
    before_bytes = f02.read_bytes()

    promo_blocked = gate.check_promotion_gate(valid_obs, target_profile="02-核心判断准则.md", confirm=False)
    assert not promo_blocked["allowed"]
    assert "G4_HUMAN_SIGNOFF_REQUIRED" in promo_blocked["failed_gates"]
    assert f02.read_bytes() == before_bytes
