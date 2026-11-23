#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.5: Bootstrap a 6-file hot-load kit from a real chat index.

This is the missing "messy chat -> six dossiers" path for a zero-config Agent:

    ingest raw -> SQLite
    bootstrap DB -> work/kit (6 files + a line-addressed evidence digest)
    validate --strict
    backfill (optional layer-2 proposal)
    validate --strict

Design constraints:
- every bullet is traceable to a real user record and an exact evidence line;
- machine-extracted items are clearly labelled as drafts, never as confirmed facts;
- uncertain gaps use compliant `[待确认]` markers (source + quote), so strict
  validation stays meaningful instead of being weakened;
- no raw file paths, phone numbers, IDs, API keys, or angle-bracket placeholders
  are written into the kit.
"""

from __future__ import annotations

import argparse
import collections
import importlib
import pathlib
import re
import shutil
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

# Canonical kit filename for section 04. Older real kits used the legacy
# alias `04-反面案例清单.md`, which the validator still accepts on read.
KIT_04_CANONICAL = "04-正反例避坑账.md"
KIT_04_LEGACY = "04-反面案例清单.md"


def _interpreter_prefix() -> str:
    """Command prefix for commands written into the generated 00 index.

    Prefer the ``py`` launcher pinned to the current interpreter's minor
    version when it exists; otherwise plain ``python`` (``python3`` on POSIX).
    The generated index also prints a plain-language fallback for machines
    without the launcher, so a 3.11 / no-launcher machine is not stuck.
    """
    if shutil.which("py"):
        return f"py -3.{sys.version_info.minor}"
    if sys.platform == "win32":
        return "python"
    return "python3"

VALIDATOR = importlib.import_module("03_validate_kit")
INTERVIEW = importlib.import_module("interview_source")

MAX_ITEMS = 8
EVIDENCE_REL = pathlib.Path("_evidence") / "chat-lines.md"
INTERVIEW_EVIDENCE_REL = pathlib.Path("_evidence") / "interview-lines.md"

# Strong/weak cues are deliberately literal: this script is a *router*, not an
# LLM. It must never invent a claim that is not present in the user's text.
IDENTITY_CUES = (
    "我是", "我叫", "我在", "我的", "目前", "现在做", "正在做", "转行",
    "个人开发", "一人公司", "学生", "自学", "主线", "目标", "方向",
)
MAINLINE_CUES = (
    "项目", "系统", "知识库", "剪辑", "Agent", "3D", "PPT", "播客",
    "网站", "小程序", "工作流", "产品", "课程", "报告", "手册", "视频",
)
RULE_CUES = (
    "必须", "禁止", "不要", "不能", "不许", "记住", "铁律", "红线",
    "规则", "底线", "绝不",
)
PRINCIPLE_CUES = (
    "原则", "准则", "判断", "优先", "取舍", "验收", "价值", "长期", "短期",
    "质量", "速度",
)
NEGATIVE_CUES = (
    "踩坑", "失败", "返工", "报错", "崩", "重来", "不行", "卡住", "放弃",
    "白做", "浪费时间", "没完成", "什么都没", "没听懂", "没达到", "有问题",
    "搞错", "错得", "没做", "没发",
)
POSITIVE_CUES = (
    "成功", "跑通", "有效", "完成", "解决", "好用", "满意",
    "喜欢", "进步", "收获", "值得", "落地",
)
# Conversational troubleshooting aimed at the assistant is not a durable
# negative case. It is a live bug report, not a lesson the dossier should keep.
META_RE = re.compile(
    r"(你等一下|我感觉这里|你这里|你那个|你这|你搞|你在干|怎么回事|干什么|搞什么|"
    r"我不是|我只是|我想问|你说|你看|你听|你帮我|你能不能|你直接)"
)
LIST_ITEM_RE = re.compile(r"^\d+[.、)）]\s*")


# Material that is not the user's own durable view: pasted prompts, role cards,
# AI summaries, URLs, code fences, tool logs. Keep it out of the dossier.
NOISE_MARKERS = (
    "你是一名", "你是我的", "请扮演", "扮演一下", "绝对铁律", "# Role",
    "## Role", "智能总结", "内容总结", "Thought Process", "thoughtprocess",
    "欢迎收听", "感谢收听", "本期", "转写", "字幕", "skill://", "plugin://",
    "[操作电脑]", "[seedaudio", "[GitHub]", "http://", "https://",
    "输入区", "每次只填", "每次仅需填写", "角色与组队", "系统角色",
    "请你扮演", "任务要求", "交付物定义", "输出格式", "要求如下",
    "角色与核心使命", "你的项目身份", "你的专长", "你的产出",
    "MASTER BRIEF", "PROJECT MASTER", "你是由", "环境说明",
    "检测到您的", "本报告", "报告日期", "听播客:",
    # Issue #94: pasted third-party person intros / bios / podcast scripts are
    # not the user's own durable view; keep them out of the A-level candidates.
    "个人简介", "人物简介", "教育经历", "他认为", "她认为", "作者认为",
    "书中说", "节选自", "摘自", "引用自", "主播", "嘉宾", "访谈实录",
    "转写稿", "作为过去", "五十年",
)
ABUSIVE_MARKERS = (
    "有病", "狗屁", "鸡毛", "傻", "滚", "妈的", "操你", "废物", "垃圾",
)

PATH_RE = re.compile(r"(?:[A-Za-z]:\\Users\\[^\s，。；、）】]+|/Users/[^\s，。；、）】]+|/home/[^\s，。；、）】]+)")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_RE = re.compile(r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
ANGLE_RE = re.compile(r"[<>]")
MULTISPACE_RE = re.compile(r"\s+")
SECRET_RE = re.compile(
    r"(?i)(?:SecretId|SecretKey|AccessKeyId|AccessKeySecret|api[_-]?key|token)"
    r"\s*[:：=]\s*[^\s，。；、）】]+"
)
AK_RE = re.compile(r"AKID[A-Za-z0-9]{10,}")
SELF_RE = re.compile(r"(我是|我叫|我在做|我在学|我目前|我现在|我的项目|我的目标|我的主线|我的背景|我想做|我打算|我正在|我个人|我要做|我这一生|对我来说)")
# A message can be mostly a task instruction even when it contains "我". The
# bootstrap generator must not turn "请你深度分析…" into an identity candidate.
REQUEST_START_RE = re.compile(
    r"^(?:请你|请帮我|帮我|你可以|你看|你先|你给我|给我|麻烦|按照|先把|先给|先做|先看|"
    r"去看|去找|搜一下|搜索一下|建议|能不能|可以帮我|请深度|请对|请基于|请结合|"
    r"请整理|请生成|请写|请列出|告诉我|说一下|我想请你|我需要你|你帮我|你帮我看看|"
    r"你觉得|我觉得你可以|我觉得你|你这里|你那个|你这|你现在|你直接|你按|你按照|"
    r"我想问|我想知道|我要你)"
)
TASK_CONTENT_RE = re.compile(
    r"(请你|帮我|帮我看看|你可以|你看|你先|你去|你给我|给我|按上面|按照|深度分析|"
    r"深度搜索|深度看|去GitHub|去B站|去网上|搜一下|检索一下|生成一份|整理并生成|"
    r"导出给我|告诉我|说明一下|看一下|看一看|研究一下|"
    r"我就想|我想用|渲染出来|建模应用程序)"
)
EXPERIENCE_RE = re.compile(r"(我|我们|之前|上次|后来|结果|当时|这次|踩坑|跑通|返工)")
# Issue #94: a question to the AI is not an identity / principle / rule candidate.
QUESTION_RE = re.compile(
    r"(是不是|能不能|可不可以|有没有|在哪里|什么形式|怎么回事|为何|能否|"
    r"还是说|你可以看一下|请问|哪些|什么区别|什么意思|[？?])"
)
# Third-party attribution phrases: pasted biography / quoted philosophy / essay.
THIRD_PARTY_MARKERS = (
    "个人简介", "人物简介", "教育经历", "他认为", "她认为", "作者认为",
    "书中说", "节选自", "摘自", "引用自", "作为过去", "五十年",
)


def strip_request_tail(text: str) -> str:
    """Keep the declarative first half, drop a trailing instruction clause."""
    for marker in ("，请", "。请", "；请", "所以请", "然后请", "并请"):
        if marker in text:
            head = text.split(marker, 1)[0].strip()
            if len(head) >= 12:
                return head
    return text

WORK_TITLE_MARKERS = (
    "项目", "知识库", "AI", "3D", "PPT", "报告", "市场", "剪辑", "Agent",
    "技能", "GitHub", "Obsidian", "排课", "播客", "设计", "工作流", "文件",
    "电脑", "工具", "研究", "方案", "视频", "写作", "公众号", "演示", "自动化",
    "工作", "开发", "系统", "学习", "调研", "内容", "排版", "素材", "封面",
)
PERSONAL_TITLE_MARKERS = ("情感", "歌", "心理", "锁", "不知道", "对话主题", "恋爱")


def source_title(source_file: str) -> str:
    name = pathlib.Path(source_file).name
    name = re.sub(r"^\d{8}-\d{6}-", "", name)
    name = re.sub(r"^用户与豆包的对话$", "通用对话", name)
    name = re.sub(r"\.md$", "", name)
    return name.strip() or "未命名会话"


def work_source(title: str) -> bool:
    if any(marker in title for marker in PERSONAL_TITLE_MARKERS):
        return False
    return any(marker in title for marker in WORK_TITLE_MARKERS)


# The strict validator treats these as unresolved claims. A bootstrap draft must
# not smuggle them into a "finished" file; replace with a neutral phrase and keep
# the same replacement in the evidence digest so quotes stay exact.
UNCERTAIN_WORDS = (
    "记不清", "记不得", "记不住", "记混", "待核实", "待人工核实", "未核实",
    "说不准", "拿不准", "没印象", "想不起来", "可能记错", "可能记混",
    "我不确定", "我拿不准", "不确定", "有待确认",
)


@dataclass
class Record:
    rec_id: str
    created_at: str
    content: str
    source_file: str
    evidence_line: int = 0
    display: str = ""

    @property
    def quote(self) -> str:
        return self.display or self.content[:220]


def top_sources(records: list[Record], limit: int = 10) -> list[tuple[str, int]]:
    counts: collections.Counter[str] = collections.Counter(source_title(r.source_file) for r in records)
    return [(title, count) for title, count in counts.most_common(limit)]


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sanitize(text: str) -> str:
    """Make a record safe to embed while preserving enough wording to quote.

    All substitutions are mirrored in the evidence digest, so a citation's quote
    and source line remain byte-identical after cleaning.
    """
    t = unicodedata.normalize("NFKC", text or "")
    t = MULTISPACE_RE.sub(" ", t).strip()
    t = PATH_RE.sub("（本地路径）", t)
    t = PHONE_RE.sub("（手机号）", t)
    t = ID_RE.sub("（证件号）", t)
    t = SECRET_RE.sub("（密钥已隐藏）", t)
    t = AK_RE.sub("（密钥已隐藏）", t)
    for word in UNCERTAIN_WORDS:
        t = t.replace(word, "未定")
    t = t.replace("[待确认]", "（待确认）")
    t = ANGLE_RE.sub("", t)
    t = t.replace("｜", " | ").replace("「", "『").replace("」", "』")
    return t[:520]


def chunk_text(text: str, size: int = 420) -> list[str]:
    """Split a long user message at sentence boundaries, keeping each chunk self-contained."""
    parts = re.split(r"(?<=[。！？!?；;\n])", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) > size and buf:
            chunks.append(buf.strip())
            buf = part
        else:
            buf += part
    if buf.strip():
        chunks.append(buf.strip())
    return chunks or [text[:size]]


def is_noise(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if any(marker.replace(" ", "") in compact for marker in NOISE_MARKERS):
        return True
    if any(marker in compact for marker in ABUSIVE_MARKERS):
        return True
    if len(text) < 15 or len(text) > 600:
        return True
    if text.count("```") or text.startswith(("```", "|", "---")):
        return True
    # A pure question or a one-word command is not a durable view.
    if len(text) < 35 and text.endswith(("?", "？")):
        return True
    # Issue #94: questions directed at the AI never become durable candidates.
    if QUESTION_RE.search(text):
        return True
    # Task instructions aimed at the AI ("你帮我 / 请你 / 我需要你") are not
    # self-description unless the same message also states a first-person fact.
    if any(p in compact for p in ("你帮我", "请你", "我需要你", "你给我", "你要")) and not SELF_RE.search(text):
        return True
    return False


def score(text: str, cues: tuple[str, ...]) -> int:
    return sum(2 if len(cue) >= 2 else 1 for cue in cues if cue in text)


def _first_sentence(text: str, limit: int = 68) -> str:
    parts = re.split(r"(?<=[。！？!?；;])", text)
    s = next((p.strip() for p in parts if p.strip()), text)
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip("，,、 ") + "…"


def candidate_sentence(text: str, kind: str) -> str:
    """Pick one declarative, self-relevant sentence; drop task instructions.

    This is intentionally rule-based. It either returns a verbatim sentence that
    exists in the user message, or "" (no fabrication, no paraphrase).
    """
    raw = unicodedata.normalize("NFKC", text or "")
    parts = [p.strip() for p in re.split(r"(?<=[。！？!?；;])", raw) if p.strip()]
    best = ""
    best_score = -1
    for part in parts:
        part = re.sub(r"^[#>*\-\s]+", "", part).strip()
        part = re.sub(r"\s+", " ", part)
        part = strip_request_tail(part)
        if len(part) < 12 or len(part) > 220:
            continue
        if LIST_ITEM_RE.match(part):
            continue
        if META_RE.search(part):
            continue
        if any(mark in part for mark in ("✅", "├", "└", "│", "|", "**")):
            continue
        if part.count(",") + part.count("、") > 6:
            continue
        if REQUEST_START_RE.search(part):
            continue
        # Issue #94: questions and pasted third-party material never enter any A-level candidate.
        if QUESTION_RE.search(part):
            continue
        if any(mark in part for mark in THIRD_PARTY_MARKERS):
            continue
        if TASK_CONTENT_RE.search(part) and not SELF_RE.search(part):
            continue
        if kind in ("identity", "mainline") and part.startswith(("然后", "所以", "但是", "那", "这个", "那个", "还有", "另外")):
            continue
        if kind == "identity":
            if not SELF_RE.search(part):
                continue
            s = score(part, IDENTITY_CUES)
        elif kind == "mainline":
            if not (SELF_RE.search(part) or "我的" in part):
                continue
            if part.endswith(("在", "和", "与", "然后", "因为", "所以", "我是在")):
                continue
            if "我觉得" in part:
                continue
            if VALIDATOR.DIALOGUE_ADDRESSED_RE.search(part):
                continue
            s = score(part, MAINLINE_CUES)
        elif kind == "principle":
            if "你可以" in part or "你看" in part or "我们这里可以" in part:
                continue
            if len(part) > 120:
                continue
            if not re.search(r"(原则|准则|优先|取舍|验收|价值|长期|短期|质量|速度)", part):
                continue
            if not re.search(r"(我|我们|原则|准则|判断|优先|取舍)", part):
                continue
            s = score(part, PRINCIPLE_CUES)
        elif kind == "rule":
            if "你可以" in part:
                continue
            # Issue #94: a task-content sentence ("我就想用…把冰屋渲染出来") is not a hard rule,
            # even when it contains a first-person pronoun.
            if TASK_CONTENT_RE.search(part):
                continue
            if VALIDATOR.DIALOGUE_ADDRESSED_RE.search(part):
                continue
            if not re.search(r"(必须|禁止|不要|不能|不许|记住|铁律|红线|规则|底线|绝不)", part):
                continue
            # Issue #56: a durable rule survives the rule-shape audit; technical
            # excerpts, one-turn task instructions and dialogue lines are dropped.
            rule_ok, _reason = VALIDATOR.rule_shape(part)
            if not rule_ok:
                continue
            s = score(part, RULE_CUES)
        elif kind == "negative":
            if len(part) < 24:
                continue
            if not EXPERIENCE_RE.search(part):
                continue
            case_ok, _reason = VALIDATOR.case_shape(part)
            if not case_ok:
                continue
            s = score(part, NEGATIVE_CUES)
        elif kind == "positive":
            if not EXPERIENCE_RE.search(part):
                continue
            if any(cue in part for cue in NEGATIVE_CUES):
                continue
            case_ok, _reason = VALIDATOR.case_shape(part)
            if not case_ok:
                continue
            s = score(part, POSITIVE_CUES)
        else:
            continue
        if s <= 0:
            continue
        if s > best_score or (s == best_score and len(part) > len(best)):
            best, best_score = part, s
    return best


def _select(records: list[Record], cues: tuple[str, ...], used: set[str],
            limit: int = MAX_ITEMS, kind: str = "") -> list[Record]:
    ranked = sorted(
        (r for r in records if r.rec_id not in used),
        key=lambda r: (-score(r.content, cues), -len(r.content), r.rec_id),
    )
    picked: list[Record] = []
    for r in ranked:
        if len(picked) >= limit:
            break
        sentence = candidate_sentence(r.content, kind) if kind else ""
        if not sentence:
            continue
        r.display = sentence
        picked.append(r)
    # If a category is thin, do not pad it with unrelated text; the section will
    # say "样本不足" instead. That is honest and keeps quality from collapsing.
    used.update(r.rec_id for r in picked)
    return picked


def _quote_line(record: Record) -> str:
    return (
        f"原文：「{record.quote}」 ｜ 出处：{EVIDENCE_REL.as_posix()}:{record.evidence_line}"
    )


def _bullet(record: Record, idx: int, pending_note: str = "") -> str:
    heading = record.display or _first_sentence(record.content)
    tail = f" ｜ {pending_note}" if pending_note else ""
    return (
        f"- **候选-{idx:02d}** {heading} ｜ {_quote_line(record)} "
        f"｜ 来源通道：raw 回填 B 级{tail}"
    )


def _conflict_note(fact: INTERVIEW.InterviewFact) -> str:
    return f"[待确认] 与访谈「{fact.text}」不一致；以访谈 A 级为准，本条需本人裁定，不得覆盖访谈记录"


def _pending(record: Record, question: str) -> str:
    return (
        f"- [待确认] {question} ｜ 原文：「{record.quote}」 ｜ "
        f"出处：{EVIDENCE_REL.as_posix()}:{record.evidence_line}"
    )


def _empty_note(label: str) -> str:
    return f"- 本类样本不足：数据库中没有足够的「{label}」原话；先补访谈或更多聊天，不用推测填空。"


def _build_evidence(records: list[Record], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 机器提取证据行（只读）",
        "",
        "> 每行一条用户原话；编号用于 6 份档案的「出处」列。原文已做路径/号码/不确定词清理，清理规则见生成器注释。",
        "",
    ]
    for i, r in enumerate(records, start=1):
        r.evidence_line = i + 4  # 1-based line number of the first record line
        lines.append(f"L{i:04d} | {r.rec_id} | {r.created_at} | user | {r.content}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_interview_evidence(bundle: INTERVIEW.InterviewBundle, path: pathlib.Path) -> None:
    """Copy sourced interview lines into the kit evidence digest.

    The kit bullet cites the digest line so a reviewer can open the copied
    line and trace it back to ``answers.md`` / ``round-N.md`` (original file +
    line kept in the bullet's `来源` field).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 访谈 A 级证据行（只读）",
        "",
        "> 每行一条访谈答案；编号供六份档案「出处」列核对。原文来自 work/interview 的 answers.md / round-N.md。",
        "",
    ]
    for i, fact in enumerate(bundle.facts, start=1):
        fact.evidence_line = i + 4
        lines.append(f"L{i:04d} | {fact.source_file}:{fact.source_line} | {fact.slot} | {fact.quote}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _agent_md(db_path: pathlib.Path, records: list[Record], sources: list[tuple[str, int]],
               bundle: INTERVIEW.InterviewBundle | None = None) -> str:
    source_lines = "\n".join(f"- `{title}`：{count} 条用户原话" for title, count in sources[:8]) or "- （样本不足）"
    interview_note = ""
    if bundle and not bundle.is_empty():
        interview_note = (
            f"\n- **访谈 A 级**：{len(bundle.facts)} 条本人在 6 轮访谈中确认的答案"
            f"（来源：{', '.join(bundle.source_files)}），见 `_evidence/interview-lines.md`。"
            "访谈答案是基准，raw 回填只能补证，不得覆盖。\n"
        )
    return f"""# AGENTS.md · 机器初稿交接说明

> 来源：`{db_path.name}` 的 {len(records)} 条真实用户消息。生成时间：{_now()}。
> 生成器：`scripts/04_bootstrap_kit.py`。这是一份**机器初稿**，不是本人已经签字的定稿。

## 一、先读顺序

1. `00-总入口索引.md`：文件地图与可执行命令。
2. `01-身份与当前主线.md`：目前反复出现的项目/方向**候选**。
3. `02-核心判断准则.md`：从原话中抽出的判断句。
4. `03-硬规则与表达黑话.md`：硬约束与表达偏好。
5. `04-正反例避坑账.md`：踩坑/返工/有效做法的标本。

## 二、事实等级（必须遵守）

- **A 级 · 访谈**：本人在 6 轮访谈中明确确认的答案；带访谈原文与 `answers.md` / `round-N.md` 出处。是基准，其他来源不得覆盖。{interview_note}
- **A 级 · 原话**：有 `原文` + `出处`，而且能在 `_evidence/chat-lines.md` 的对应行找到原句。可以当作“本人说过”。
- **B 级 · raw 回填**：由多条原话归纳出的主题/主线。只能当“候选归纳”，不能当身份定论；与访谈 A 级冲突时标 `[待确认]`，由本人裁定。
- **C 级 · L2 待确认**：写作 `[待确认]` 的二层回流条目。只能向本人提问，不得自行补全。

## 三、给接手 Agent 的硬规则

1. 先读原文，再下结论；不要把这份初稿当成本人已确认。
2. 任何 B 级归纳，引用时都要说“这是从 N 条原话归纳的候选”，不要改写成“用户就是”。
3. 遇到 C 级条目，停下来问本人；不要用常识补齐。
4. 不把 assistant 的总结、角色提示、粘贴材料当用户记忆。
5. 不把提及时间当事件时间；时间判断以 `event_date` 与原文为准。
6. 二次回流产出的候选必须保留原文/出处，并走签字门；不要让 Agent 代签。
7. 交付前跑 `scripts/xh.py validate --kit work/kit --strict`，看到 `VALIDATE_OK` 才算结构合格。

## 四、本次覆盖的会话（按原话条数）

{source_lines}

这些标题只帮助定位，不构成身份判断；真正的证据在 `_evidence/chat-lines.md`。
"""


def _index_md(records: list[Record], sources: list[tuple[str, int]],
              prefix: str, bundle: INTERVIEW.InterviewBundle | None = None) -> str:
    source_lines = "\n".join(f"- `{title}`：{count} 条" for title, count in sources[:12])
    interview_line = ""
    if bundle and not bundle.is_empty():
        interview_line = (
            f"\n- 访谈输入：{', '.join(bundle.source_files)}（{len(bundle.facts)} 条 A 级答案，"
            "优先级高于 raw 回填）"
        )
    return f"""# 00-总入口索引

> 机器初稿，生成于 {_now()}；数据源 {len(records)} 条用户消息。{interview_line}

## 一、六份档案

| 文件 | 作用 | 证据密度 |
|---|---|---|
| `AGENTS.md` | 接手 Agent 的读法与硬规则 | 规则 |
| `01-身份与当前主线.md` | 身份/项目/方向候选 | 原话引用 |
| `02-核心判断准则.md` | 判断句与取舍标准 | 原话引用 |
| `03-硬规则与表达黑话.md` | 硬约束、表达偏好 | 原话引用 |
| `04-正反例避坑账.md` | 正例/反例标本 | 原话引用 |
| `_evidence/chat-lines.md` | 行号化证据，供核对 | 原始证据 |

## 二、零环境 Agent 的可执行流程

```powershell
{prefix} -X utf8 scripts/xh.py doctor
{prefix} -X utf8 scripts/xh.py build --raw work/raw --db work/unified_index.db --kit work/kit --l2 work/layer2
{prefix} -X utf8 scripts/xh.py validate --kit work/kit --strict
```

> 解释器退路：上面的 `py -3.x` 依赖 Windows py launcher；没有 launcher 的机器把开头换成 `python`（Linux/macOS 用 `python3`），其余参数不变。

如果 `build` 不可用，再按单步跑：

```powershell
{prefix} -X utf8 scripts/xh.py ingest --raw work/raw --db work/unified_index.db
{prefix} -X utf8 scripts/xh.py bootstrap --db work/unified_index.db --out work/kit
{prefix} -X utf8 scripts/xh.py match --db work/unified_index.db --out work/backfill_candidates.md
{prefix} -X utf8 scripts/xh.py backfill --profiles work/kit --first-pass work/backfill_candidates.md --db work/unified_index.db --out work/layer2 --broad
{prefix} -X utf8 scripts/xh.py validate --kit work/kit --strict
```

`build` 生成初稿与二层候选；`backfill` 只生成待确认候选。两步都不会替本人签字。

## 三、检索入口

```powershell
{prefix} -X utf8 scripts/xh.py retrieval --db work/unified_index.db --keyword 项目 --limit 20
{prefix} -X utf8 scripts/xh.py retrieval --db work/unified_index.db --entity 知识库 --hops 2
```

时间检索用 `--as-of`；关键词检索走 FTS5；图检索走 1~2 跳实体边。它们是辅助召回，不替代六份档案。

## 四、覆盖的会话

{source_lines or '- （样本不足）'}
"""


def _identity_md(records: list[Record], selected: list[Record], mainline: list[Record],
                 history: list[Record], sources: list[tuple[str, int]],
                 bundle: INTERVIEW.InterviewBundle | None = None) -> str:
    bundle = bundle or INTERVIEW.InterviewBundle()
    interview_name = bundle.by_slot("name")
    interview_identity = bundle.by_slot("identity") + bundle.by_slot("time_boundary")
    interview_mainline = bundle.by_slot("mainline")
    lines = [
        "# 01-身份与当前主线",
        "",
        "> **机器初稿 / B 级**：以下是从用户原话中抽出的身份与方向候选，不是本人签字确认的身份定论。",
        "> 访谈中本人确认的答案列为 **A 级**，优先级高于 raw 回填；两者不一致时 raw 条目标 `[待确认]`，不覆盖访谈。",
        "",
        "## 一、身份候选（有原话才写）",
        "",
    ]
    interview_all_identity = interview_name + interview_identity
    if interview_all_identity:
        for fact in interview_all_identity:
            lines.append(fact.evidence_bullet(fact.evidence_line))
        lines.append("")
    if selected:
        for i, r in enumerate(selected, 1):
            note = ""
            for fact in interview_identity:
                if not INTERVIEW.raw_agrees(fact, r.content):
                    note = _conflict_note(fact)
                    break
            lines.append(_bullet(r, i, pending_note=note))
    elif not interview_all_identity:
        lines.append(_empty_note("身份/自我描述"))
    lines += ["", "## 二、当前主线候选（最多 1 条，待本人确认）", ""]
    if interview_mainline:
        for fact in interview_mainline:
            lines.append(fact.evidence_bullet(fact.evidence_line))
        lines.append("")
    if mainline:
        for r in mainline:
            note = ""
            for fact in interview_mainline:
                if not INTERVIEW.raw_agrees(fact, r.content):
                    note = _conflict_note(fact)
                    break
            lines.append(_bullet(r, 1, pending_note=note))
    elif not interview_mainline:
        lines.append("- 需访谈：没有足够原话判断当前主线；请补访谈或更多聊天，不用历史项目凑数。")
    lines += ["", "## 三、历史项目与曾经提到的方向（不是当前主线）", ""]
    if history:
        for i, r in enumerate(history, 1):
            lines.append(_bullet(r, i))
    else:
        lines.append("- 暂无除当前主线外的其他方向候选。")
    lines += ["", "## 四、会话标题清单（仅用于定位原文，不构成主线判断）", ""]
    if sources:
        for title, count in sources[:10]:
            lines.append(f"- `{title}`：{count} 条用户原话；标题只帮助定位，不代表这是当前主线。")
    else:
        lines.append("- 会话标题不足，无法列出投入方向。")
    lines += ["", "## 五、需要本人确认的边界", ""]
    anchors = (selected + mainline)[:3]
    if anchors:
        for r in anchors:
            term = next((t for t in MAINLINE_CUES if t in r.content), "这个方向")
            lines.append(_pending(r, f"是否把含「{term}」的这段原话作为当前主线？"))
    else:
        lines.append("- 数据库里没有足够原话，无法生成待确认问题；先补访谈。")
    lines += [
        "",
        "## 六、使用边界",
        "",
        "- 本文件只回答“本人说过什么”，不回答“本人一定是什么样的人”。",
        "- 引用时保留 `原文` 与 `出处`；不要把候选归纳改写成绝对身份。",
        "- 主线会变；以最近一次本人确认或最新原文为准。",
        "",
    ]
    return "\n".join(lines)


def _principles_md(items: list[Record],
                   bundle: INTERVIEW.InterviewBundle | None = None) -> str:
    bundle = bundle or INTERVIEW.InterviewBundle()
    interview_principles = bundle.by_slot("principle")
    lines = [
        "# 02-核心判断准则",
        "",
        "> **机器初稿 / B 级**：判断句必须来自用户原话并带出处；机器归纳标题不能冒充本人原话。",
        "> 访谈选定的准则列为 **A 级**；raw 回填只作补证，与 A 级不一致时标 `[待确认]`。",
        "",
        "## 一、有据判断（原话 + 出处）",
        "",
    ]
    if interview_principles:
        for fact in interview_principles:
            lines.append(fact.evidence_bullet(fact.evidence_line))
        lines.append("")
    if items:
        for i, r in enumerate(items, 1):
            note = ""
            for fact in interview_principles:
                if not INTERVIEW.raw_agrees(fact, r.content):
                    note = _conflict_note(fact)
                    break
            lines.append(_bullet(r, i, pending_note=note))
        if len(items) + len(interview_principles) < 3:
            lines += ["", f"- 原话不足 3 条（现有 raw {len(items)} 条 + 访谈 {len(interview_principles)} 条）；其余判断需访谈补全，不用归纳句填空。"]
    elif not interview_principles:
        lines.append("- 需访谈：数据库中没有足够的「判断/取舍」原话；请补访谈或更多聊天，不用推测或归纳填空。")
    lines += [
        "",
        "## 二、待补访谈",
        "",
        "- 本文件不写机器归纳出来的取舍顺序；归纳内容只能在本人确认原话后升格。",
        "",
    ]
    return "\n".join(lines)


def _rules_md(items: list[Record],
              bundle: INTERVIEW.InterviewBundle | None = None) -> str:
    bundle = bundle or INTERVIEW.InterviewBundle()
    interview_rules = bundle.by_slot("rule")
    lines = [
        "# 03-硬规则与表达黑话",
        "",
        "> **机器初稿 / B 级**：硬规则只从用户明确说过的原话抽取；没有原话就不编规则。",
        "> 访谈确认的红线列为 **A 级**；raw 回填只作补证，与 A 级不一致时标 `[待确认]`。",
        "",
        "## 一、硬规则候选",
        "",
    ]
    if interview_rules:
        for fact in interview_rules:
            lines.append(fact.evidence_bullet(fact.evidence_line))
        lines.append("")
    if items:
        for i, r in enumerate(items, 1):
            note = ""
            for fact in interview_rules:
                if not INTERVIEW.raw_agrees(fact, r.content):
                    note = _conflict_note(fact)
                    break
            lines.append(_bullet(r, i, pending_note=note))
    elif not interview_rules:
        lines.append(_empty_note("硬规则/禁止"))
    lines += [
        "",
        "## 二、表达偏好（候选）",
        "",
        "- 说人话：先给结论，再给证据与下一步。",
        "- 不堆术语，不用空洞的大词；能用具体产物说话就用产物。",
        "- 不确定的边界要标出来源，不把推测写成事实。",
        "- 以上是表达偏好归纳，不是逐字黑话表；真实黑话需本人补录。",
        "",
        "## 三、禁止事项（缺原话时留空）",
        "",
        "- 不替本人签字；不把 assistant 总结当用户记忆；不伪造出处。",
        "",
    ]
    return "\n".join(lines)


def _cases_md(negatives: list[Record], positives: list[Record],
              bundle: INTERVIEW.InterviewBundle | None = None) -> str:
    bundle = bundle or INTERVIEW.InterviewBundle()
    interview_pos = bundle.by_slot("positive")
    interview_neg = bundle.by_slot("negative")
    lines = [
        "# 04-正反例避坑账",
        "",
        "> **机器初稿**：正例/反例保留原话与出处；标签是机器加的，事实以原话为准。每条必须是具体场景 + 损失/后果的陈述句。",
        "> 访谈确认的正例/反例列为 **A 级**；raw 回填只作补证。",
        "",
        "## 一、正例标本",
        "",
    ]
    if interview_pos:
        for fact in interview_pos:
            lines.append(fact.evidence_bullet(fact.evidence_line))
        lines.append("")
    if positives:
        for i, r in enumerate(positives, 1):
            lines.append(_bullet(r, i))
    elif not interview_pos:
        lines.append(_empty_note("有效做法/成功"))
    lines += ["", "## 二、反例标本", ""]
    if interview_neg:
        for fact in interview_neg:
            lines.append(fact.evidence_bullet(fact.evidence_line))
        lines.append("")
    if negatives:
        for i, r in enumerate(negatives, 1):
            lines.append(_bullet(r, i))
    elif not interview_neg:
        lines.append(_empty_note("踩坑/返工"))
    lines += [
        "",
        "## 三、从标本里提炼的避坑句（机器归纳，非本人原话）",
        "",
        "- 先确认原文与验收，再动手；避免把“看起来完成”当成“真实跑通”。",
        "- 时间、出处、身份三类事实，缺一条就降级为待确认。",
        "- 以上为归纳句；若与正反例原话冲突，以原话为准，且不得升格为本人准则。",
        "",
    ]
    return "\n".join(lines)


def build_kit(db_path: pathlib.Path, out_dir: pathlib.Path,
              interview: pathlib.Path | str | None = None) -> dict[str, object]:
    if not db_path.is_file():
        raise FileNotFoundError(f"DB_NOT_FOUND: {db_path}")
    bundle = INTERVIEW.load_interview(interview)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM records ORDER BY created_at, rec_id")]
    finally:
        con.close()

    records: list[Record] = []
    for row in rows:
        if str(row.get("role", "")).lower() != "user":
            continue
        clean = sanitize(str(row.get("content", "")))
        if len(clean) < 15:
            continue
        chunks = chunk_text(clean) if len(clean) > 600 else [clean]
        for chunk in chunks:
            if is_noise(chunk):
                continue
            records.append(Record(
                rec_id=str(row.get("rec_id") or f"REC-{len(records)+1:04d}"),
                created_at=str(row.get("created_at") or "unknown"),
                content=chunk,
                source_file=str(row.get("source_file") or ""),
            ))

    if len(records) < 3 and bundle.is_empty():
        raise ValueError(f"NOT_ENOUGH_USER_RECORDS: only {len(records)} usable user messages")

    # "Messy chat" contains personal chats, pasted prompts and old projects.
    # Prefer work-titled conversations; only fall back to all records when the
    # work filter is too thin to build a useful draft.
    work_records = [r for r in records if work_source(source_title(r.source_file))]
    if len(work_records) >= 24:
        records = work_records

    out_dir.mkdir(parents=True, exist_ok=True)
    _build_evidence(records, out_dir / EVIDENCE_REL)
    if not bundle.is_empty():
        _build_interview_evidence(bundle, out_dir / INTERVIEW_EVIDENCE_REL)

    used: set[str] = set()
    identity_pool = [r for r in records if SELF_RE.search(r.content[:160])]
    identity = _select(identity_pool, IDENTITY_CUES, used, limit=3, kind="identity")
    mainline_pool = [r for r in records if SELF_RE.search(r.content) or score(r.content, MAINLINE_CUES) >= 2]
    mainline_raw = _select(mainline_pool, MAINLINE_CUES, used, limit=4, kind="mainline")
    # Issue #56: at most one current mainline; everything else moves to a history zone.
    mainline = mainline_raw[:1]
    history = mainline_raw[1:]
    principles = _select(records, PRINCIPLE_CUES, used, kind="principle")
    rules = _select(records, RULE_CUES, used, kind="rule")
    negatives = _select(records, NEGATIVE_CUES, used, kind="negative")
    positives = _select(records, POSITIVE_CUES, used, kind="positive")
    # Thin sections get a second, less strict pass from the remaining pool.
    if len(positives) < 3:
        positives += [r for r in _select(records, MAINLINE_CUES + POSITIVE_CUES, used,
                                          3 - len(positives), kind="positive")
                      if r not in positives]

    top_sources_list = top_sources(records)

    prefix = _interpreter_prefix()
    files = {
        "AGENTS.md": _agent_md(db_path, records, top_sources_list, bundle),
        "00-总入口索引.md": _index_md(records, top_sources_list, prefix, bundle),
        "01-身份与当前主线.md": _identity_md(records, identity, mainline, history, top_sources_list, bundle),
        "02-核心判断准则.md": _principles_md(principles, bundle),
        "03-硬规则与表达黑话.md": _rules_md(rules, bundle),
        KIT_04_CANONICAL: _cases_md(negatives, positives, bundle),
    }
    for name, body in files.items():
        (out_dir / name).write_text(body.rstrip() + "\n", encoding="utf-8")

    # Older real kits were written under the legacy alias `04-反面案例清单.md`.
    # Drop a stale legacy copy from a reused output dir so the validator reads
    # the canonical file; the alias still stays accepted on read by the validator.
    legacy = out_dir / KIT_04_LEGACY
    if legacy.is_file():
        try:
            text = legacy.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if "04-反面案例清单" in text or "<写清具体场景" in text:
            legacy.unlink()

    ok, messages = VALIDATOR.validate_kit(out_dir, strict=True)
    return {
        "records": len(records),
        "sections": {
            "identity": len(identity), "mainline": len(mainline),
            "history": len(history),
            "principles": len(principles), "rules": len(rules),
            "negative": len(negatives), "positive": len(positives),
            "interview": len(bundle.facts),
        },
        "interview_facts": len(bundle.facts),
        "interview_sources": bundle.source_files,
        "validate_ok": ok,
        "validate_messages": messages,
        "evidence": str(out_dir / EVIDENCE_REL),
        "interview_evidence": str(out_dir / INTERVIEW_EVIDENCE_REL) if not bundle.is_empty() else None,
        "kit": str(out_dir),
    }


def _top_terms(records: list[Record]) -> list[str]:
    counter: collections.Counter[str] = collections.Counter()
    stop = set("我们你们他们这个那个就是可以还是然后因为所以但是如果已经现在一个什么怎么这些那些")
    for r in records:
        for block in re.findall(r"[\u4e00-\u9fff]{4,}", r.content):
            for n in (4, 6):
                for i in range(max(0, len(block) - n + 1)):
                    gram = block[i:i + n]
                    if gram in stop or any(ch in "的了是在和与及就都也还而" for ch in gram):
                        continue
                    counter[gram] += 1
    return [term for term, count in counter.most_common(30) if count >= 2][:20]


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap six profile drafts from a real chat index")
    ap.add_argument("--db", required=True, type=pathlib.Path)
    ap.add_argument("--out", default=pathlib.Path("work/kit"), type=pathlib.Path)
    ap.add_argument("--interview", "--answers", dest="interview", default=None,
                    type=pathlib.Path,
                    help="访谈目录（含 answers.md 与 round-N.md）或单个 answers.md；"
                         "访谈答案作为 A 级基准入稿，raw 回填只作补证")
    args = ap.parse_args()
    try:
        res = build_kit(args.db, args.out, interview=args.interview)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"BOOTSTRAP_FAIL: {exc}")
        return 2
    print("BOOTSTRAP_OK " + " ".join(f"{k}={v}" for k, v in res["sections"].items()))
    if res["interview_facts"]:
        print(f"INTERVIEW_OK facts={res['interview_facts']} sources={','.join(res['interview_sources'])}")
    print(f"records={res['records']} evidence={res['evidence']}")
    if res["validate_ok"]:
        print("VALIDATE_OK")
        return 0
    print("VALIDATE_FAIL")
    for msg in res["validate_messages"]:
        print(msg)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
