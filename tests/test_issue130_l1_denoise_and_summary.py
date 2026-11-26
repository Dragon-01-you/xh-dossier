#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #130: L1 prompt/one-turn-directive denoising + per-step conversion summary + intent doc."""

from __future__ import annotations

import importlib
import json
import pathlib
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

BOOTSTRAP = importlib.import_module("04_bootstrap_kit")
VALIDATOR = importlib.import_module("03_validate_kit")


def _make_db(tmp_path: pathlib.Path, rows: list[tuple[str, str, str, str, str]]) -> pathlib.Path:
    db = tmp_path / "chat.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    con.executemany(
        "INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
        [(a, b, c, d, e, f"m{i}", "", "stated") for i, (a, b, c, d, e) in enumerate(rows)],
    )
    con.commit()
    con.close()
    return db


def test_l1_filters_pasted_prompts_and_one_turn_directives_but_keeps_standing_rules(
    tmp_path: pathlib.Path,
) -> None:
    rows = [
        # Pasted prompts / templates that MUST NOT enter 02 or 03:
        ("REC-0001", "20261101-100000-项目设计.md", "2026-11-01", "user",
         "产品哲学:状态优先——用户先选状态(静心/专注/阅读/放松/助眠),声音是达成状态的手段。"),
        ("REC-0002", "20261101-100100-项目设计.md", "2026-11-01", "user",
         "【核心原则】所有输出必须严格按以下 JSON 结构返回，优先保证字段齐全。"),
        ("REC-0003", "20261101-100200-调研.md", "2026-11-01", "user",
         "你是一位参与多委员交叉评审的独立委员,请就下面这个真实研究问题给出独立回答,不要迎合题干。"),
        ("REC-0004", "20261101-100300-调研.md", "2026-11-01", "user",
         "你是深度研究子智能体,用 Google/YouTube/Reddit 等等不要局限于这些平台抓英文一手长文全文。"),
        ("REC-0005", "20261101-100400-项目设计.md", "2026-11-01", "user",
         "通用规则(所有层级共用,放在最前面) 规则一:数据源固定,不用回忆。"),
        ("REC-0006", "20261101-100500-项目设计.md", "2026-11-01", "user",
         "你输出的所有内容必须是可验证、可复制、可对齐真实决策的底层系统,绝对不允许做普通的人物分析。"),
        # Single-turn ephemeral / continuation directives that MUST NOT enter 02 or 03:
        ("REC-0007", "20261102-100000-系统开发.md", "2026-11-02", "user",
         "继续上面没有完成的不要从新开始，先把刚才那个列表接着输出完。"),
        ("REC-0008", "20261102-100100-系统开发.md", "2026-11-02", "user",
         "关于解决用户的问题,不能这么简单，再展开分析一下这个界面。"),
        ("REC-0009", "20261102-100200-系统开发.md", "2026-11-02", "user",
         "我觉得这里的话,它是可以不要的。"),
        ("REC-0010", "20261102-100300-系统开发.md", "2026-11-02", "user",
         "这四张必须是同一个世界的不同视角。"),
        # Genuine durable personal principles & rules that MUST BE KEPT:
        ("REC-0011", "20261103-100000-工作流.md", "2026-11-03", "user",
         "我的判断原则是先对齐目标与真实需求，再谈方法骨架与工具，宁可慢一点也不能方向跑偏。"),
        ("REC-0012", "20261103-100100-工作流.md", "2026-11-03", "user",
         "动手前必须先确认方案，严禁不经同意改原件，所有测试都在隔离副本里跑。"),
        ("REC-0013", "20261103-100200-工作流.md", "2026-11-03", "user",
         "硬规则：同一个报错连试两次不通必须换思路，不要原地死循环。"),
        ("REC-0014", "20261103-100300-工作流.md", "2026-11-03", "user",
         "我正在做个人知识库自动化项目，目标是沉淀可复核的长期记忆档案。"),
    ]
    db = _make_db(tmp_path, rows)
    kit = tmp_path / "kit"
    res = BOOTSTRAP.build_kit(db, kit)
    assert res["validate_ok"], res["validate_messages"]

    p02 = (kit / "02-核心判断准则.md").read_text(encoding="utf-8")
    p03 = (kit / "03-硬规则与表达黑话.md").read_text(encoding="utf-8")

    # Noise must be filtered out of 02 & 03:
    for bad in (
        "产品哲学",
        "【核心原则】",
        "独立委员",
        "子智能体",
        "通用规则",
        "普通的人物分析",
        "继续上面没有完成的",
        "关于解决用户的问题",
        "可以不要的",
        "这四张必须",
    ):
        assert bad not in p02, f"noise leaked into 02: {bad}"
        assert bad not in p03, f"noise leaked into 03: {bad}"

    # Genuine durable principles & rules must survive:
    assert "先对齐目标与真实需求" in p02
    assert "动手前必须先确认方案" in p03 or "严禁不经同意改原件" in p03
    assert "同一个报错连试两次不通必须换思路" in p03


def test_build_prints_and_writes_stage_conversion_summary(tmp_path: pathlib.Path) -> None:
    raw = ROOT / "examples" / "sample_raw"
    db = tmp_path / "u.db"
    kit = tmp_path / "kit"
    kit_next = tmp_path / "kit_next"
    l2 = tmp_path / "l2"
    report = tmp_path / "report.md"

    proc = subprocess.run(
        [
            sys.executable, "-X", "utf8", str(ROOT / "scripts" / "xh.py"), "build",
            "--raw", str(raw),
            "--db", str(db),
            "--kit", str(kit),
            "--kit-next", str(kit_next),
            "--l2", str(l2),
            "--report", str(report),
            "--interview", str(ROOT / "examples" / "sample_interview"),
            "--skip-retrieval",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # Preserve existing CLI contract tokens
    assert "BUILD_OK" in proc.stdout
    assert "VALIDATE_OK" in proc.stdout
    # Human-readable stage conversion summary in stdout
    assert "PIPELINE_SUMMARY" in proc.stdout
    assert "输入" in proc.stdout and "过滤" in proc.stdout and "产出" in proc.stdout

    # Persisted summary report beside kit
    summary_file = tmp_path / "build_summary.md"
    assert summary_file.is_file(), "expected build_summary.md next to kit"
    summary_text = summary_file.read_text(encoding="utf-8")
    assert "阶段转化摘要" in summary_text
    assert "待本人确认" in summary_text
    assert "过滤" in summary_text

    # Build receipt points to summary
    receipt = json.loads((ROOT / "work" / "xh-build.json").read_text(encoding="utf-8"))
    assert receipt.get("summary") == str(summary_file)


def test_agent_start_here_documents_intent_and_fallback_boundaries_without_local_paths() -> None:
    doc = (ROOT / "AGENT_START_HERE.md").read_text(encoding="utf-8")
    assert "流程意图" in doc
    assert "兜底" in doc
    assert "停手问人" in doc or "必须停手" in doc
    # No personal machine home paths leaked into docs
    for forbidden in ("C:\\Users\\", "/Users/", "/home/"):
        assert forbidden not in doc
