#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #131: L2 recall expansion (rhetorical ? & long spoken reflection) + normalized L1 dedup."""

from __future__ import annotations

import importlib
import pathlib
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

L2 = importlib.import_module("05_deep_backfill")
BOOT = importlib.import_module("04_bootstrap_kit")
L2_APPLY = importlib.import_module("08_l2_apply")


def _make_profiles(base: pathlib.Path, extra_03: str = "") -> pathlib.Path:
    base.mkdir(parents=True, exist_ok=True)
    for name in L2.PROFILE_FILES:
        body = f"# {name}\n普通档案正文，用于覆盖率对照测试。\n"
        if name == "03-硬规则与表达黑话.md" and extra_03:
            body += "\n" + extra_03 + "\n"
        (base / name).write_text(body, encoding="utf-8")
    return base


def _make_db(path: pathlib.Path, recs: list[tuple[str, str, str, str, str]]) -> pathlib.Path:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE records (rec_id TEXT PRIMARY KEY, source_file TEXT, created_at TEXT, "
        "role TEXT, content TEXT, md5 TEXT, event_date TEXT, date_kind TEXT)"
    )
    con.executemany(
        "INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
        [(a, b, c, d, e, f"md5-{i}", "", "stated") for i, (a, b, c, d, e) in enumerate(recs)],
    )
    con.commit()
    con.close()
    return path


def test_rhetorical_question_reflection_kept_while_pure_ai_question_rejected() -> None:
    reflection = (
        "今天复盘，我觉得核心问题是：做了一天啥也没做出来。"
        "直到晚上最后，实在没有办法再拍一条几秒钟或一分多钟的视频吗？"
        "我觉得核心问题一开始就错了，我今天修了一天这个 bug，其实它根本就没有那个问题。"
        "关于测试，首先我觉得我做错了，最快的测试方法其实是拿另一台电脑去真实体验。"
    )
    ok, reason = L2.classify_narrative(reflection)
    assert ok is True, f"rhetorical reflection must not be killed: {reason}"

    for pure_q in (
        "请问这个报错怎么修？",
        "帮我看看这段代码能不能直接跑起来？",
        "在 GitHub 上为什么还需要我们主动去保护 main 分支？不然的话会覆盖吗？",
    ):
        q_ok, q_reason = L2.classify_narrative(pure_q)
        assert q_ok is False and q_reason == "non_personal:question", (pure_q, q_ok, q_reason)


def test_long_spoken_reflection_kept_while_pasted_report_or_code_rejected() -> None:
    long_spoken = (
        "今天做完这一轮复盘，我发现自己最大的问题就是每次都卡在最后一个环节不敢发布。"
        "上次把静态网站改了六天，每天都在微调颜色和边距，结果拖到错过活动截止日期，白做了整整一周。"
        "后来我仔细回想，其实并不是代码没写完，而是我心里总怕别人觉得不够完美，所以反复返工。"
        "今天复盘又碰到同样的问题，本机跑得挺顺，一发给别人就因为环境变量报错，我居然又想自己闷头修一天。"
        "我觉得以后必须给自己定死时间盒，到点就先发最小可用版本给真人试跑，拿到反馈再改。"
    ) * 3  # ~720 chars natural first-person prose
    assert len(long_spoken) > 600
    ok, reason = L2.classify_narrative(long_spoken)
    assert ok is True, f"long spoken reflection should pass (>600 chars): {reason}"

    pasted_code_report = (
        "# 架构评测报告\n\n## 背景\n\n## 指标对比\n\n## 结论\n\n"
        "| 引擎 | 延迟 | 备注 |\n|---|---|---|\n| A | 12ms | 正常 |\n| B | 40ms | 较慢 |\n\n"
        "```python\nfor i in range(10):\n    print(i)\n```\n"
        + ("我这里贴一段外部技术文档用于参考，详情见正文分析与表格数据。" * 20)
    )
    assert len(pasted_code_report) > 600
    p_ok, p_reason = L2.classify_narrative(pasted_code_report)
    assert p_ok is False, f"pasted structured doc/code must be rejected: {p_reason}"


def test_l2_deduplicates_fullwidth_halfwidth_punctuation_against_l1(tmp_path: pathlib.Path) -> None:
    # L1 kit holds the sentence with half-width comma/colon (as sanitized by 04_bootstrap_kit.py),
    # while SQLite holds the exact same sentence with full-width comma/colon.
    l1_rule = "记住,动手前必须先确认方案,未经本人同意严禁改原件。"
    raw_rule = "记住，动手前必须先确认方案，未经本人同意严禁改原件。"
    untold_rec = "上次我做完小工具一直没发出去，拖了四天返工，结果错过截止日期实在太累。"

    profiles_dir = _make_profiles(
        tmp_path / "profiles",
        extra_03=(
            f"- **候选-01** {l1_rule} ｜ 原文：「{l1_rule}」 ｜ "
            "出处：_evidence/chat-lines.md:5 ｜ 来源通道：raw 回填 B 级"
        ),
    )
    ev = profiles_dir / "_evidence"
    ev.mkdir()
    (ev / "chat-lines.md").write_text(
        "# 证据\n\n> 只读\n\n"
        f"L0001 | REC-0001 | 2026-11-01 | user | {l1_rule}\n",
        encoding="utf-8",
    )

    fp = tmp_path / "fp.md"
    fp.write_text("# 一层报告\n- [REC-0099 | 2026-11-01] 占位待确认\n", encoding="utf-8")
    db = _make_db(
        tmp_path / "chat.db",
        [
            ("REC-0001", "20261101-100000-工作流.md", "2026-11-01", "user", raw_rule),
            # Same text even under a DIFFERENT rec_id (e.g. duplicate wording with spacing diff)
            ("REC-0002", "20261102-100000-工作流.md", "2026-11-02", "user",
             "记住， 动手前必须先确认方案 ，未经本人同意严禁改原件！"),
            ("REC-0003", "20261103-100000-复盘.md", "2026-11-03", "user", untold_rec),
        ],
    )

    res = L2.run_deep_backfill(profiles_dir, fp, db, tmp_path / "l2_out", broad=True)
    report_text = pathlib.Path(res["report"]).read_text(encoding="utf-8")
    assert "REC-0001" not in report_text, "exact L1 rec_id/text must not reappear in L2"
    assert "REC-0002" not in report_text, "punctuation-variant duplicate of L1 must not reappear in L2"
    assert "REC-0003" in report_text, "genuinely untold personal setback must still be surfaced"


def test_afterchat_sanitized_sample_yields_nonzero_l2_reflection_candidates(tmp_path: pathlib.Path) -> None:
    afterchat_dir = ROOT / "samples" / "fresh-test" / "afterchat"
    assert afterchat_dir.is_dir()
    db = tmp_path / "ac.db"
    kit = tmp_path / "kit"
    kit_next = tmp_path / "kit_next"
    l2_dir = tmp_path / "l2"
    report = tmp_path / "fp.md"

    proc = subprocess.run(
        [
            sys.executable, "-X", "utf8", str(ROOT / "scripts" / "xh.py"), "build",
            "--raw", str(afterchat_dir),
            "--db", str(db),
            "--kit", str(kit),
            "--kit-next", str(kit_next),
            "--l2", str(l2_dir),
            "--report", str(report),
            "--skip-retrieval",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "L2_BACKFILL_OK" in proc.stdout
    l2_md = (l2_dir / "l2_candidates.md").read_text(encoding="utf-8")
    assert "L2-0001" in l2_md, f"expected >0 L2 candidates on afterchat sample:\n{l2_md}"
    assert "今天复盘" in l2_md or "我做错了" in l2_md or "分发给别人很难" in l2_md
    # Official kit body must remain unsigned/unchanged by L2 pending candidates.
    assert "二层回流待确认区" not in (kit / "04-正反例避坑账.md").read_text(encoding="utf-8")
