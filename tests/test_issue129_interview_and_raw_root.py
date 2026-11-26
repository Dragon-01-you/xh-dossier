#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #129: Real interview prefill-card absorption + --raw-root channel isolation."""

from __future__ import annotations

import importlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

INTERVIEW = importlib.import_module("interview_source")
BOOTSTRAP = importlib.import_module("04_bootstrap_kit")
VALIDATOR = importlib.import_module("03_validate_kit")

PREFILL_CARD_MD = """# 访谈预填卡：合成回归样例

> 状态：全部 `[待确认]`。

## 先复述：我目前读到的核心判断（待你确认）

1. 做事顺序是 **目标 → 骨架 → 招式 → 工具**：先对齐需求，再谈工具。
2. **做完不交付 = 0**：到时间盒先发最简可用版，不能停在半成品。

---

## 第 1 轮：AI 人设与表达（→ `AGENTS.md`）

### Q1. 合作遇分歧时，希望 AI 怎么站位？

- A 顺从助手：你说啥就照做；
- B 严谨合伙人（推荐）：先对齐目标，有逻辑漏洞直接拿事实顶回来；

**AI 预填：B** `[待确认]`

### Q3. 最反感 AI 哪些废话/越界？

- A “这是一个非常好的问题/多维度赋能”等水话；
- B 没查文件就瞎猜“大概可以”；
- C 不经同意删改原文件。

**AI 预填：A + B + C 全选** `[待确认]`

---

## 第 3 轮：当前项目与现实约束（→ `01-身份与当前主线.md`）

### Q1. 此刻唯一核心项目/任务是什么？

**AI 预填：**
- 长期主线：`[待确认]` “工具工程化实践”，面向初学者；
- 当前任务：`[待确认]` “记忆冷库验收闭环”：把零散记录变成可校验六份档案。

### Q2. 时间/阶段/能力上的硬约束？

- A 每天只有晚间 1-2 小时；
- B 当前阶段重点是跑通闭环、消化看懂，不急着商业化；

**AI 预填：B** `[待确认]`

---

## 第 4 轮：核心判断与验收（→ `02-核心判断准则.md`）

### Q2. 什么硬标准才算“真做成”？

- A 外部真用户跑通并收回反馈；
- B 本地测试全绿并能脱稿讲明白；
- C 两者都要（内外双验收）。

**AI 预填：C** `[待确认]`

---

## 第 5 轮：硬规则与黑话（→ `03-硬规则与表达黑话.md`）

### Q1. 操作文件/排查报错，哪几条绝对不能碰？

- A 原始导出只读，不直接写主知识库；
- B 同一个报错连试 2 次不通就换方案；

**AI 预填：A + B（不代签字、不伪造）** `[待确认]`

### Q2. 现在统一怎么称呼？

**AI 预填：** 统一称呼“林舟”；账号“linzhou_dev” `[待确认]`

---

## 第 6 轮：正例与反例（→ `04-反面案例清单.md`）

### Q1. 哪 1–2 件事让你觉得“这套做法必须永远固化”？

**AI 预填：**
1. 接外部工具前先建隔离镜像，零损护住原库 `[待确认]`；
2. 重要任务先定验收再动手，本人最终签字 `[待确认]`。

### Q2. 哪 1–2 个坑需要 AI 一看见苗头就拦停？

**AI 预填：**
1. 盲目堆功能却停在 80% 不发布 `[待确认]`；
2. 没查原文就直接凭记忆下结论 `[待确认]`。

---

## 你回来时怎么用

1. 只看每题的 AI 预填，回选项即可。
2. 确认完才生成正式 6 份。
"""


def _run_xh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "xh.py"), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_prefill_card_parses_all_core_slots_and_skips_usage_section(tmp_path: pathlib.Path) -> None:
    card = tmp_path / "访谈预填卡.md"
    card.write_text(PREFILL_CARD_MD, encoding="utf-8")

    bundle = INTERVIEW.load_interview(card)
    assert not bundle.is_empty(), "prefill card must not parse to 0 facts"
    assert len(bundle.facts) >= 8

    assert bundle.get("name") is not None and "林舟" in bundle.get("name").text
    assert bundle.by_slot("identity"), "expected identity/stage fact"
    assert bundle.by_slot("mainline"), "expected mainline fact"
    assert bundle.by_slot("principle"), "expected principle facts"
    assert bundle.by_slot("rule"), "expected rule facts"
    assert bundle.by_slot("positive"), "expected positive facts"
    assert bundle.by_slot("negative"), "expected negative facts"

    # Usage instructions must not leak into personal dossier facts.
    all_texts = "\n".join(f.text for f in bundle.facts)
    assert "只看每题的" not in all_texts
    assert "确认完才生成正式" not in all_texts


def test_empty_or_unparseable_interview_emits_clear_warning(tmp_path: pathlib.Path) -> None:
    bad_card = tmp_path / "broken_interview.md"
    bad_card.write_text("# 随便写的笔记\n\n这里没有任何可解析的访谈结构。\n", encoding="utf-8")
    db = tmp_path / "chat.db"
    raw = ROOT / "examples" / "sample_raw"

    ingest = _run_xh("ingest", "--raw", str(raw), "--db", str(db), "--query", "记错")
    assert ingest.returncode == 0, ingest.stdout + ingest.stderr

    kit = tmp_path / "kit"
    boot = _run_xh("bootstrap", "--db", str(db), "--out", str(kit), "--interview", str(bad_card))
    assert boot.returncode == 0, boot.stdout + boot.stderr
    combined = boot.stdout + boot.stderr
    assert "INTERVIEW_WARN" in combined
    assert "0" in combined


def test_build_and_strict_validate_with_raw_root_does_not_false_fail_interview(tmp_path: pathlib.Path) -> None:
    card = tmp_path / "访谈预填卡.md"
    card.write_text(PREFILL_CARD_MD, encoding="utf-8")
    raw = ROOT / "examples" / "sample_raw"
    db = tmp_path / "u.db"
    kit = tmp_path / "kit"
    kit_next = tmp_path / "kit_next"
    l2 = tmp_path / "l2"
    report = tmp_path / "report.md"

    build = _run_xh(
        "build",
        "--raw", str(raw),
        "--db", str(db),
        "--kit", str(kit),
        "--kit-next", str(kit_next),
        "--l2", str(l2),
        "--report", str(report),
        "--interview", str(card),
        "--skip-retrieval",
    )
    assert build.returncode == 0, build.stdout + build.stderr
    assert "interview=0" not in build.stdout

    # Strict + enforce-score + --raw-root must have 0 RAW_ZERO_HIT on legal interview bullets.
    val = _run_xh(
        "validate",
        "--kit", str(kit_next),
        "--strict",
        "--enforce-score",
        "--raw-root", str(raw),
    )
    assert val.returncode == 0, val.stdout + val.stderr
    assert "RAW_ZERO_HIT" not in val.stdout
    assert "VALIDATE_OK" in val.stdout

    # Also verify standard sample_interview passes --raw-root cleanly.
    kit_std = tmp_path / "kit_std"
    boot_std = _run_xh(
        "bootstrap", "--db", str(db), "--out", str(kit_std),
        "--interview", str(ROOT / "examples" / "sample_interview"),
    )
    assert boot_std.returncode == 0, boot_std.stdout + boot_std.stderr
    val_std = _run_xh(
        "validate", "--kit", str(kit_std), "--strict", "--enforce-score", "--raw-root", str(raw)
    )
    assert val_std.returncode == 0, val_std.stdout + val_std.stderr
    assert "RAW_ZERO_HIT" not in val_std.stdout
    assert "VALIDATE_OK" in val_std.stdout


def test_fabricated_chat_raw_quote_still_caught_by_raw_root(tmp_path: pathlib.Path) -> None:
    raw = ROOT / "examples" / "sample_raw"
    db = tmp_path / "u.db"
    kit = tmp_path / "kit"

    assert _run_xh("ingest", "--raw", str(raw), "--db", str(db), "--query", "记错").returncode == 0
    assert _run_xh(
        "bootstrap", "--db", str(db), "--out", str(kit),
        "--interview", str(ROOT / "examples" / "sample_interview"),
    ).returncode == 0

    # Inject a fabricated chat quote into BOTH _evidence/chat-lines.md and 02-核心判断准则.md
    # so file/line citation passes, leaving --raw-root as the decisive check.
    fake_quote = "这是一句凭空编造且绝对不存在于原始聊天导出里的假判断句。"
    ev_path = kit / "_evidence" / "chat-lines.md"
    ev_lines = ev_path.read_text(encoding="utf-8").splitlines()
    ev_lines.append(f"L9999 | REC-9999 | 2026-11-26 | user | {fake_quote}")
    ev_path.write_text("\n".join(ev_lines) + "\n", encoding="utf-8")
    fake_lineno = len(ev_lines)

    p02 = kit / "02-核心判断准则.md"
    text02 = p02.read_text(encoding="utf-8")
    fake_bullet = (
        f"- **A级·原话** {fake_quote} ｜ 原文：「{fake_quote}」 ｜ "
        f"出处：_evidence/chat-lines.md:{fake_lineno} ｜ 来源通道：raw 回填 A 级"
    )
    text02 = text02.replace("## 一、有据判断（原话 + 出处）\n", f"## 一、有据判断（原话 + 出处）\n\n{fake_bullet}\n", 1)
    p02.write_text(text02, encoding="utf-8")

    val = _run_xh(
        "validate", "--kit", str(kit), "--strict", "--enforce-score", "--raw-root", str(raw)
    )
    assert val.returncode != 0, val.stdout + val.stderr
    assert "RAW_ZERO_HIT" in val.stdout
    assert "02-核心判断准则.md: RAW_ZERO_HIT" in val.stdout
    assert "01-身份与当前主线.md: RAW_ZERO_HIT" not in val.stdout
    assert "03-硬规则与表达黑话.md: RAW_ZERO_HIT" not in val.stdout
    assert "VALIDATE_OK" not in val.stdout
    assert "VALIDATE_FAIL" in val.stdout


def test_prefill_card_skips_hollow_other_option_and_option_ref_parentheticals(
    tmp_path: pathlib.Path,
) -> None:
    sample = """# 访谈预填卡：P2 边角回归样例

## 第 2 轮：多平台与知识库地图

### Q3. 今天说的和旧记录打架，按什么裁决？

- A 一律听旧记录；
- B 主客二分：称呼听今天，代码状态看客观原文；
- C 全部 `[待确认]`，翻原文再拍板。

**AI 预填：B（不确定项加 C）** `[待确认]`

## 第 4 轮：核心判断与验收

### Q1. 面对新方案，优先顺序？

- A 目标与真需求 → 方法骨架 → 招式 → 工具；
- B 先做最快原型碰人，再补原理；

**AI 预填：A（B 作为补充）** `[待确认]`

## 第 1 轮：表达顺序

### Q2. 表达顺序怎么排？

- A 结论先行：白话讲底层再贴命令；
- C 看任务切换：熟活直接给结果，陌生机制先问清；

**AI 预填：C（主线 A）** `[待确认]`

## 第 5 轮：硬规则与黑话

### Q1. 哪几条绝对不能碰？

- A 原始导出只读，不直接写主知识库；
- B 连试 2 次不通就换方案；
- C 其他特定禁令。

**AI 预填：A + B + C（不代签字、不伪造）** `[待确认]`
"""
    card = tmp_path / "访谈预填卡.md"
    card.write_text(sample, encoding="utf-8")
    bundle = INTERVIEW.load_interview(card)
    joined = "\n".join(f.text for f in bundle.facts)

    # Spurious unselected options, parenthetical meta option refs, and hollow options must be dropped.
    assert "翻原文再拍板" not in joined
    assert "不确定项加 C" not in joined
    assert "B 作为补充" not in joined
    assert "先做最快原型碰人" not in joined
    assert "其他特定禁令" not in joined
    assert "`" not in joined

    # Primary choices, explicit `（主线 A）` pick, and real non-letter inline supplements must stay.
    assert "称呼听今天，代码状态看客观原文" in joined
    assert "目标与真需求" in joined
    assert "熟活直接给结果" in joined
    assert "白话讲底层再贴命令" in joined
    assert "原始导出只读" in joined
    assert "不代签字、不伪造" in joined

