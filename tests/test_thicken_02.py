#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #150 / T7: 02 gets sourced judgements and the mainline collapses to one.

The tests only look at external behaviour — the bytes of the six kit files and
the scorecard — never at the selector's internals.
"""

import hashlib
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

THICKEN = importlib.import_module("14_thicken_02")
VALIDATOR = importlib.import_module("03_validate_kit")

PADDING = (
    "先确认目标与验收，再谈执行速度",
    "先保真实与可复现，再谈漂亮表达",
    "先做最小闭环，再扩规模",
)

EVIDENCE_SENTENCES = [
    ("REC-0001", "2026-09-13", "其实我学编程,核心是为了解决问题。"),
    ("REC-0001", "2026-09-13", "所以,我需要先明确一个具体目标,而不是盲目地学很多内容。"),
    ("REC-0002", "2026-10-02", "本质上,我们是要把这些做到极致的。"),
    ("REC-0003", "2026-10-20",
     "每次我跟他协作的时候,不是他一直在做,而是我能从他的过程中真实地提取到洞察。"),
    # Noise the selector must refuse.
    ("REC-0004", "2026-10-21", "请帮我详细规划一下学习路线,主要包含以下两条路径。"),
    ("REC-0005", "2026-10-21", "你觉得这个方案到底行不行?"),
    ("REC-0006", "2026-10-22", "你这里的数据分析不行，返工了三次。"),
    # Rows backing the untouched 03 / 04 bullets (citations must resolve).
    ("REC-0007", "2026-10-23", "必须保留原文出处,不要编造没有发生的事。"),
    ("REC-0008", "2026-10-24", "这次跑通了,有效的做法是每步都给产物和退出码。"),
    ("REC-0009", "2026-10-25", "上一版没做出来,白做了一周。"),
    # Rows backing 01's identity / mainline bullets.
    ("REC-0010", "2026-10-26", "我是个人开发者,平时主要做自己的项目。"),
    ("REC-0011", "2026-10-26", "我要做一个 3D 可视化项目,帮助理解编程原理。"),
    ("REC-0012", "2026-10-27", "我现在有一个排课的项目,主要是给中小学排课。"),
    ("REC-0013", "2026-10-27", "我的知识库每天免费调用次数有限。"),
]
RULE_LINE = 12
POSITIVE_LINE = 13
NEGATIVE_LINE = 14
IDENTITY_LINE = 15
MAINLINE_LINE = 16
DEMOTED_LINE_1 = 17
DEMOTED_LINE_2 = 18


def _evidence(rows) -> str:
    lines = [
        "# 机器提取证据行（只读）",
        "",
        "> 每行一条用户原话。",
        "",
    ]
    for idx, (rec, date, text) in enumerate(rows, start=1):
        lines.append(f"L{idx:04d} | {rec} | {date} | user | {text}")
    return "\n".join(lines) + "\n"


def _kit(tmp_path: pathlib.Path, rows=None) -> pathlib.Path:
    rows = EVIDENCE_SENTENCES if rows is None else rows
    kit = tmp_path / "kit"
    (kit / "_evidence").mkdir(parents=True)
    (kit / "_evidence" / "chat-lines.md").write_text(_evidence(rows), encoding="utf-8")
    (kit / "AGENTS.md").write_text("# AGENTS\n\n交接说明正文，足够长的正常档案内容。\n", encoding="utf-8")
    (kit / "00-总入口索引.md").write_text("# 00\n\n索引正文，足够长的正常档案内容。\n", encoding="utf-8")
    (kit / "01-身份与当前主线.md").write_text(
        "# 01-身份与当前主线\n\n"
        "## 一、身份候选（有原话才写）\n\n"
        "- **候选-01** 我是个人开发者。 ｜ 原文：「我是个人开发者,平时主要做自己的项目。」 ｜ "
        f"出处：_evidence/chat-lines.md:{IDENTITY_LINE}\n\n"
        "## 二、当前主线候选\n\n"
        "- **候选-01** 我要做一个 3D 可视化项目。 ｜ 原文：「我要做一个 3D 可视化项目,帮助理解编程原理。」 ｜ "
        f"出处：_evidence/chat-lines.md:{MAINLINE_LINE}\n"
        "- **候选-02** 我现在有一个排课的项目。 ｜ 原文：「我现在有一个排课的项目,主要是给中小学排课。」 ｜ "
        f"出处：_evidence/chat-lines.md:{DEMOTED_LINE_1}\n"
        "- **候选-03** 我的知识库调用次数有限。 ｜ 原文：「我的知识库每天免费调用次数有限。」 ｜ "
        f"出处：_evidence/chat-lines.md:{DEMOTED_LINE_2}\n\n"
        "## 三、从会话标题看到的投入方向\n\n"
        "- `3D可视化项目研究规划`：5 条用户原话；是否为当前主线，需本人确认。\n\n"
        "## 四、需要本人确认的边界\n\n"
        "- [待确认] 是否把这段原话作为当前主线？ ｜ 原文：「我要做一个 3D 可视化项目,帮助理解编程原理。」 ｜ "
        f"出处：_evidence/chat-lines.md:{MAINLINE_LINE}\n\n"
        "## 五、使用边界\n\n"
        "- 本文件只回答“本人说过什么”。\n",
        encoding="utf-8",
    )
    (kit / "02-核心判断准则.md").write_text(
        "# 02-核心判断准则\n\n"
        "## 一、先验证再下结论\n\n"
        "- 本类样本不足：数据库中没有足够的「判断/取舍」原话。\n\n"
        "## 二、取舍顺序（候选）\n\n"
        + "".join(f"- {sentence}\n" for sentence in PADDING)
        + "- 以上三条是归纳，不是本人原话；如与原话冲突，以原话为准。\n",
        encoding="utf-8",
    )
    (kit / "03-硬规则与表达黑话.md").write_text(
        "# 03-硬规则与表达黑话\n\n## 一、硬规则候选\n\n"
        "- **候选-01** 必须保留原文出处，不要编造没有发生的事。 ｜ "
        "原文：「必须保留原文出处,不要编造没有发生的事。」 ｜ "
        f"出处：_evidence/chat-lines.md:{RULE_LINE}\n",
        encoding="utf-8",
    )
    (kit / "04-正反例避坑账.md").write_text(
        "# 04-正反例避坑账\n\n## 一、正例标本\n\n"
        "- **候选-01** 这次跑通了，有效的做法是每步都给产物和退出码。 ｜ "
        "原文：「这次跑通了,有效的做法是每步都给产物和退出码。」 ｜ "
        f"出处：_evidence/chat-lines.md:{POSITIVE_LINE}\n\n"
        "## 二、反例标本\n\n"
        "- **候选-02** 上一版没做出来，白做了一周。 ｜ "
        "原文：「上一版没做出来,白做了一周。」 ｜ "
        f"出处：_evidence/chat-lines.md:{NEGATIVE_LINE}\n",
        encoding="utf-8",
    )
    return kit


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bullet_lines(text: str, heading_keyword: str) -> list[str]:
    in_section = False
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = heading_keyword in line
            continue
        if in_section and line.startswith("- **候选"):
            out.append(line)
    return out


def test_thicken_fills_principle_slot_and_collapses_mainline(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    summary = THICKEN.run(kit, limit=5, dry_run=False)

    assert summary["result"] == "DONE"
    assert summary["principle_before"] == 0
    assert summary["principle_after"] >= 3
    assert summary["mainline_before"] == 3
    assert summary["mainline_after"] == 1

    text02 = (kit / "02-核心判断准则.md").read_text(encoding="utf-8")
    bullets = _bullet_lines(text02, "有据判断")
    assert len(bullets) >= 3
    for bullet in bullets:
        assert "原文：" in bullet and "出处：" in bullet
        assert VALIDATOR._verify_pending_source(bullet, kit) == ""

    text01 = (kit / "01-身份与当前主线.md").read_text(encoding="utf-8")
    assert len(_bullet_lines(text01, "当前主线候选")) == 1


def test_scorecard_passes_after_thicken(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    before = VALIDATOR.score_kit(kit)
    assert "principle" in before["missing_slots"]
    assert before["metrics"]["mainline_unique"]["passed"] is False

    THICKEN.run(kit, limit=5, dry_run=False)
    after = VALIDATOR.score_kit(kit)

    assert after["missing_slots"] == []
    assert after["metrics"]["coverage"]["passed"] is True
    assert after["metrics"]["answerable_questions"]["passed"] is True
    assert after["metrics"]["citation_accuracy"]["passed"] is True
    assert after["metrics"]["mainline_unique"]["passed"] is True
    assert after["overall_passed"] is True


def test_thicken_never_touches_03_and_04(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    frozen = {name: _digest(kit / name) for name in THICKEN.FROZEN if (kit / name).is_file()}
    assert frozen, "fixture must contain the frozen files"

    THICKEN.run(kit, limit=5, dry_run=False)

    for name, digest in frozen.items():
        assert _digest(kit / name) == digest, f"{name} must stay byte-identical"


def test_second_run_is_a_noop(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    THICKEN.run(kit, limit=5, dry_run=False)
    snapshot = {p.name: _digest(p) for p in kit.glob("*.md")}

    summary = THICKEN.run(kit, limit=5, dry_run=False)

    assert summary["result"] == "NOOP"
    assert {p.name: _digest(p) for p in kit.glob("*.md")} == snapshot


def test_padding_sentences_are_gone(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    THICKEN.run(kit, limit=5, dry_run=False)
    text02 = (kit / "02-核心判断准则.md").read_text(encoding="utf-8")
    for sentence in PADDING:
        assert sentence not in text02
    assert "本类样本不足" not in text02


def test_demoted_mainline_keeps_the_original_bytes(tmp_path: pathlib.Path) -> None:
    kit = _kit(tmp_path)
    path = kit / "01-身份与当前主线.md"
    original = path.read_text(encoding="utf-8")
    demoted = _bullet_lines(original, "当前主线候选")[1:]

    THICKEN.run(kit, limit=5, dry_run=False)
    updated = path.read_text(encoding="utf-8")

    for line in demoted:
        assert line in updated.splitlines(), "降级只移动、不改写：原句与出处必须逐字保留"


def test_thin_evidence_is_honest_not_padded(tmp_path: pathlib.Path) -> None:
    rows = [
        ("REC-0001", "2026-09-13", "请帮我详细规划一下学习路线，主要包含两条路径。"),
        ("REC-0002", "2026-09-14", "你觉得这个方案到底行不行?"),
    ]
    kit = _kit(tmp_path, rows=rows)
    summary = THICKEN.run(kit, limit=5, dry_run=False)

    assert summary["principle_after"] == 0
    text02 = (kit / "02-核心判断准则.md").read_text(encoding="utf-8")
    assert "需访谈" in text02 or "样本不足" in text02
    for sentence in PADDING:
        assert sentence not in text02


def test_selector_refuses_requests_questions_and_dialogue() -> None:
    assert THICKEN.judge_sentences("请帮我详细规划一下学习路线。") == []
    assert THICKEN.judge_sentences("你觉得这个方案到底行不行?") == []
    assert THICKEN.judge_sentences("你这里的数据分析不行，返工了三次。") == []
    assert THICKEN.judge_sentences("我觉得你可以深入看一下数据分析的本质。") == []


def test_selector_keeps_a_verbatim_tradeoff() -> None:
    sentence = "所以,我需要先明确一个具体目标,而不是盲目地学很多内容。"
    found = THICKEN.judge_sentences(f"然后我就在想。{sentence}")
    assert [text for _score, text in found] == [sentence]
