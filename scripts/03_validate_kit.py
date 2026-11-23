#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 4: Validate a 6-file AI onboarding kit for completeness, clichés, placeholders, and PII/local-path leaks."""

from __future__ import annotations

import argparse
import calendar
import collections
import pathlib
import re
import unicodedata

# Issue #2 / #15 scope (all merged on main):
#   - Bug A: cliché check no longer skips a whole line merely because it contains
#     禁止/严禁/...; only an intentional quoted example after a rule verb is exempt.
#   - Impossible calendar dates (INVALID_DATE) hard-fail in both modes.
#   - Bug B: an unsourced/bare `[待确认]` fails under --strict (PENDING_UNTRACEABLE);
#     a compliant marker stays INFO.
#   - Bug C: natural-language doubt without a literal marker (记不清/待核实/说不准...)
#     hard-fails in both modes as UNCERTAIN_SEMANTIC.
#   - #15: a cited source must resolve inside the kit dir or an explicitly approved
#     --source-root; absolute/drive-letter/`..` citations are traversal and fail.
REQUIRED_KIT_FILES = [
    "AGENTS.md",
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
]

# Real user kits often name the fourth file 04-反面案例清单.md. Accept that
# spelling without weakening the six-file contract or the output filenames.
KIT_FILE_ALIASES = {
    "04-正反例避坑账.md": ["04-反面案例清单.md", "04-正反例避坑账.md"],
}


def find_kit_file(target_dir: pathlib.Path, canonical: str) -> pathlib.Path | None:
    for name in KIT_FILE_ALIASES.get(canonical, [canonical]):
        candidate = target_dir / name
        if candidate.is_file():
            return candidate
    return None

AI_CLICHES = [
    "这是一个非常好的问题",
    "从多维度赋能",
    "打造全链路闭环生态",
    "每天进步1%复利37倍",
]

# Issue #2 / review E4: only a *quoted example adjacent to a rule verb* is exempt.
# A line merely containing 禁止 somewhere used to exempt every cliché on it.
_QUOTE_PAIRS = [
    ("'", "'"), ('"', '"'), ("`", "`"), ("“", "”"),
    ("‘", "’"), ("「", "」"), ("『", "』"), ("《", "》"), ("〈", "〉"),
]
_RULE_VERBS = ("禁止", "严禁", "不要说", "禁用水话", "别说", "禁止说", "禁止用", "严禁说", "不使用")
_RULE_CONNECTORS = ("", "说", "用", "写", "提", "出现", "输出", "：", ":", " ")

_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")
_CJK_DATE_RE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")


def _is_quoted_rule_example(line: str, cliche: str) -> bool:
    """Return True only for 禁止说“...” style intentional citations.

    A rule may list several quoted phrases in a row ("禁止说“A”“B”…"), so the
    rule verb must appear before the cliché and the span between them must not
    cross a sentence terminator. This still rejects
    “A”这是禁止的腔调, where the rule verb appears after the citation.
    """
    for open_q, close_q in _QUOTE_PAIRS:
        quoted = f"{open_q}{cliche}{close_q}"
        if quoted not in line:
            continue
        cliche_at = line.find(quoted)
        for verb in _RULE_VERBS:
            for conn in _RULE_CONNECTORS:
                marker = f"{verb}{conn}{open_q}"
                rule_at = line.find(marker)
                if rule_at == -1 or rule_at >= cliche_at:
                    continue
                if not re.search(r"[。！？；\n]", line[rule_at:cliche_at]):
                    return True
    return False


def _invalid_calendar_dates(text: str) -> list[str]:
    """Return impossible dates such as 2025-02-30; ignore month-only/version-like strings."""
    bad: list[str] = []
    for regex in (_DATE_RE, _CJK_DATE_RE):
        for m in regex.finditer(text):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (2000 <= y <= 2100 and 1 <= mo <= 12):
                bad.append(m.group(0))
                continue
            if not (1 <= d <= calendar.monthrange(y, mo)[1]):
                bad.append(m.group(0))
    return bad

# Match unfilled template instruction placeholders, both Chinese (<填写...>) and
# ASCII (<YYYY-MM>, <your_name>, <TODO>). Exclude real autolinks such as
# <https://example.com> and <mailto:...>.
PLACEHOLDER_RE = re.compile(r"<(?!(?:https?://|mailto:))[^>\n]{2,100}>")
# Runtime variables such as `<任务>` / `<项目>` / `<日期>` / `<分支>` are semantic
# slots, not unfilled template fields. Keep them visible to users, but do not fail
# strict validation for them.
RUNTIME_VAR_RE = re.compile(r"<(?:任务|项目|日期|分支)>")
# Detect accidentally leaked local user paths or secrets outside sanitized sample examples.
# Each pattern is anchored on a format that is unambiguous in prose, to keep false
# positives near zero on real Chinese kit files (dates, versions, counts must not fire).
SENSITIVE_PATH_RE = re.compile(
    r"(?:"
    # Local user home paths: only the homedir segment is sensitive, not any absolute path.
    r"[A-Za-z]:\\Users\\[^\\\s]+"
    r"|/Users/[^/\s]+"
    r"|/home/[^/\s]+"
    # OpenAI-style keys
    r"|sk-[A-Za-z0-9]{16,}"
    # GitHub tokens: ghp_/gho_/ghu_/ghs_/ghr_ + 36 chars, or fine-grained github_pat_
    r"|gh[pousr]_[A-Za-z0-9]{36,}"
    r"|github_pat_[A-Za-z0-9_]{22,}"
    # AWS access key id
    r"|AKIA[0-9A-Z]{16}"
    # Tencent Cloud / generic cloud keys (bootstrap already masks these; the
    # validator is the second line of defence against hand-written files).
    r"|AKID[A-Za-z0-9]{10,}"
    r"|(?:SecretId|SecretKey|AccessKeyId|AccessKeySecret)\s*[:：=]\s*[A-Za-z0-9/+=]{8,}"
    # PRC mobile number: 1[3-9] + 9 digits, bounded so long digit runs do not match.
    r"|(?<!\d)1[3-9]\d{9}(?!\d)"
    # PRC resident ID: 6-digit area + 8-digit birthdate + 3 digits + checksum (digit or X).
    # Anchor the birth date to a plausible 19xx/20xx range to avoid matching stray numbers.
    r"|(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
    r")"
)


# `[待确认]` tri-state scanning (CONFLICT-05 / issue #15):
# - A compliant marker: `[待确认] <疑点> ｜ 原文：「…」 ｜ 出处：<file>:<line>` -> INFO, never fails.
# - B bare marker: no source/quote -> PENDING_UNTRACEABLE in strict mode.
# - C meta-rule reference inside inline backticks or a fenced code block -> not counted.
#
# Bug B (issue #2): the strict failure on a bare marker conflicts with SKILL.md rule 4.
# That conflict is NOT relaxed here; the provenance-checking fix lands on the #15 branch
# (feat/t15-citation-check). Bug C: this scanner only matches the literal PENDING_TOKEN;
# natural-language uncertainty (记不清 / 待核实 / 说不准 / ...) is detected by the
# UNCERTAIN_PROSE channel in PR #47 (feat/t2c-uncertain-prose).
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FENCE_RE = re.compile(r"^\s*```")
PENDING_TOKEN = "[待确认]"
HAS_QUOTE_RE = re.compile(r"原文\s*[:：]\s*\S")
HAS_SOURCE_RE = re.compile(r"出处\s*[:：]\s*\S")
SOURCE_REF_RE = re.compile(r"出处\s*[:：]\s*(?P<src>[^｜|]+)")
QUOTE_TEXT_RE = re.compile(r"原文\s*[:：]\s*(?:「(?P<q1>.*?)」|“(?P<q2>.*?)”|\"(?P<q3>.*?)\"|'(?P<q4>.*?)')")
SOURCE_LINE_RE = re.compile(r"^(?P<path>.*?):(?P<line>\d+)(?:-\d+)?$")
_ABS_REF_RE = re.compile(r"^(?:[A-Za-z]:|[\\/])")
# Issue #2 Bug C: natural-language uncertainty is the same unresolved claim as a
# literal [待确认] marker. Keep the list narrow on purpose: broad words like
# "模糊/不确定" occur in legitimate rules ("把模糊想法变清晰").
UNCERTAIN_SEMANTIC_RE = re.compile(
    r"(记不清|记不得|记不住|记混|待核实|待人工核实|未核实|说不准|拿不准|没印象|想不起来|可能记错|可能记混|我不确定|我拿不准)"
)


# --- Issue #56 semantic predicates (shared by generator 04 and this audit) ---
# A durable rule must be a standing self-constraint ("遇到 X → 必须/绝不 Y"),
# not a one-turn task instruction, a technical research excerpt, or a line spoken
# at the assistant during a chat.

# License names, rendering engines, font names, design tokens: technical excerpts.
TECH_EXCERPT_RE = re.compile(
    r"(OFL|BSD-?3?|MIT\b|Apache-?2?\.?0?|ISC\b|GPL|WeasyPrint|Typst|Observable Plot|"
    r"Charter|YuMincho|思源宋|仓耳今楷|渲染器|排版系统|内嵌\s*SVG|SVG\s*图表|"
    r"#[0-9A-Fa-f]{6}|设计\s*token|画布色|强调色|行距|@page|HTML/CSS→PDF|CJK\s*规则)"
)
# Single-turn deliverable / MVP acceptance conditions, not a standing rule.
SINGLE_TASK_RE = re.compile(
    r"(MVP\s*阶段|阶段只需实现|无限次读取|无限次调用|无限调用|单独做生图素材|"
    r"\d+\s*(个)?(视图|资产|素材|模板)|三视图|生图素材|这\s*\d+\s*个视图|"
    r"MCP 还是 Skill|无论形式是 MCP)"
)
# A sentence addressed to the assistant in this turn ("你…"), not a durable view.
DIALOGUE_ADDRESSED_RE = re.compile(
    r"(我说叫你|我说了|我又没叫你|我要你|不然我要你|你安排完|你最后|是你的提示词|"
    r"你帮我|你可以看一下|你看一下|你去|你给我|你直接|你先把|你先给|你按照|"
    r"你能不能|你深度|你帮我看看|你就是要|你不能|你不要|你别|你切记|切记哈)"
)
# A standing rule is not a one-off wish / taste statement ("我要的是顶尖设计…").
RULE_WISH_RE = re.compile(r"^(?:我要的是|我想要的是)")
# A request / question aimed at the assistant, not a declarative specimen.
REQUEST_CASE_RE = re.compile(
    r"(我要你|不然我要你|怎么搜|你帮我|请你|请帮我|告诉我|我想问|我想知道|帮我看看)"
)
QUESTION_END_RE = re.compile(r"[？?]\s*$")
# Outcome / experience cue required for a positive or negative specimen case.
CASE_OUTCOME_RE = re.compile(
    r"(跑通|踩坑|返工|失败|浪费|白做|没完成|卡住|不行|完成|解决|有效|好用|满意|"
    r"喜欢|进步|收获|值得|落地|报错|崩|放弃|没听懂|没达到|搞错|学到|提升)"
)
# "能不能 / 可不可以 / 怎不能" contain 不能 but are questions, not prohibitions.
RULE_VERB_RE = re.compile(
    r"(必须|禁止|不要|不许|绝不|记住|铁律|红线|规则|底线|(?<![怎可能])不能)"
)

# Hard-coded machine padding that must never stand in for sourced principles.
PRINCIPLE_PADDING_RE = re.compile(
    r"(先确认目标与验收，再谈执行速度|先保真实与可复现，再谈漂亮表达|先做最小闭环，再扩规模)"
)
# Issue #94 advisory: question-looking candidates and pasted third-party material.
QUESTION_ANY_RE = re.compile(
    r"(是不是|能不能|可不可以|有没有|在哪里|什么形式|还是说|请问|什么区别|什么意思)"
)
PASTED_MATERIAL_TOKENS = (
    "个人简介", "人物简介", "教育经历", "他认为", "她认为", "作者认为",
    "书中说", "节选自", "摘自", "引用自", "作为过去", "五十年",
)


def rule_shape(text: str) -> tuple[bool, str]:
    """Return (is_durable_rule, reject_reason) for a candidate rule sentence."""
    if not RULE_VERB_RE.search(text):
        return False, "no-rule-verb"
    if TECH_EXCERPT_RE.search(text):
        return False, "technical-excerpt"
    if SINGLE_TASK_RE.search(text):
        return False, "single-task-instruction"
    if DIALOGUE_ADDRESSED_RE.search(text):
        return False, "dialogue-addressed"
    if RULE_WISH_RE.search(text):
        return False, "wish-preference"
    return True, ""


def case_shape(text: str) -> tuple[bool, str]:
    """Return (is_declarative_case, reject_reason) for a positive/negative specimen."""
    if QUESTION_END_RE.search(text):
        return False, "question"
    if REQUEST_CASE_RE.search(text):
        return False, "request"
    if DIALOGUE_ADDRESSED_RE.search(text):
        return False, "dialogue-addressed"
    if not CASE_OUTCOME_RE.search(text):
        return False, "no-outcome-cue"
    return True, ""


SemanticFinding = collections.namedtuple(
    "SemanticFinding", ["code", "file", "line", "message"]
)


def _section_lines(lines: list[str], heading_keyword: str) -> list[tuple[int, str]]:
    """Return (line_no, text) bullets inside the first section whose heading matches."""
    in_section = False
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        if line.startswith("## "):
            in_section = heading_keyword in line
            continue
        if in_section and line.startswith("- **候选"):
            out.append((lineno, line))
    return out


# --- Issue #96 scorecard: decidable "good enough" metrics on top of structure ---

# Slot -> (kit file canonical, section heading keyword). A slot counts as filled
# only when it holds at least one sourced bullet (raw candidate or A-level
# interview fact), not an empty note or a machine padding sentence.
SCORE_SLOTS: dict[str, tuple[str, str]] = {
    "identity": ("01-身份与当前主线.md", "身份候选"),
    "mainline": ("01-身份与当前主线.md", "当前主线候选"),
    "principle": ("02-核心判断准则.md", "有据判断"),
    "rule": ("03-硬规则与表达黑话.md", "硬规则"),
    "positive": ("04-正反例避坑账.md", "正例"),
    "negative": ("04-正反例避坑账.md", "反例"),
}

# Three blind-test questions (issue #98) answered from the kit alone.
ANSWERABLE_QUESTIONS = {
    "身份是谁": "identity",
    "当前主线": "mainline",
    "判断准则": "principle",
}

# Default thresholds; issue #96 leaves the exact cut lines for the user to
# tune. They are exposed as constants so a call site can override them.
SCORE_THRESHOLDS: dict[str, float] = {
    "coverage": 0.8,                  # filled slots / 6
    "answerable_questions": 2 / 3,    # answered questions / 3
    "citation_accuracy": 0.9,         # resolvable sourced bullets / checked
    "mainline_unique": 1.0,           # 1 when mainline has <= 1 candidate
}

_BULLET_PREFIXES = ("- **候选", "- **A级·访谈")


def _is_sourced_bullet(line: str) -> bool:
    return line.startswith(_BULLET_PREFIXES) and bool(HAS_QUOTE_RE.search(line)) and bool(HAS_SOURCE_RE.search(line))


def _slot_bullets(target_dir: pathlib.Path, slot: str) -> list[tuple[str, str]]:
    file_name, heading = SCORE_SLOTS[slot]
    fpath = find_kit_file(target_dir, file_name)
    if fpath is None:
        return []
    lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
    in_section = False
    out: list[tuple[str, str]] = []
    for line in lines:
        if line.startswith("## "):
            in_section = heading in line
            continue
        if in_section and _is_sourced_bullet(line):
            out.append((fpath.name, line))
    return out


def score_kit(
    target_dir: pathlib.Path,
    source_roots: list[pathlib.Path] | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, object]:
    """Compute decidable quality metrics for a kit.

    Metrics:
    - coverage: filled sourced slots / 6;
    - answerable_questions: blind-test questions answerable from the kit / 3;
    - citation_accuracy: sourced bullets whose source resolves in the kit / checked;
      noise rate is the complement;
    - mainline_unique: mainline section holds at most one sourced candidate.

    The scorecard never invents facts: an empty section counts as unfilled, and
    an unresolved citation counts against accuracy.
    """
    th = dict(SCORE_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    slot_bullets = {slot: _slot_bullets(target_dir, slot) for slot in SCORE_SLOTS}
    filled = {slot: bool(bullets) for slot, bullets in slot_bullets.items()}
    missing_slots = [slot for slot, ok in filled.items() if not ok]

    coverage = sum(filled.values()) / len(SCORE_SLOTS)
    answered = [q for q, slot in ANSWERABLE_QUESTIONS.items() if filled[slot]]
    answerable = len(answered) / len(ANSWERABLE_QUESTIONS)

    checked: list[tuple[str, str]] = [b for bullets in slot_bullets.values() for b in bullets]
    unresolved: list[str] = []
    for file_name, line in checked:
        reason = _verify_pending_source(line, target_dir, source_roots)
        if reason:
            unresolved.append(f"{file_name}: {reason}")
    accuracy = 1.0 if not checked else (len(checked) - len(unresolved)) / len(checked)
    noise_rate = 1.0 - accuracy

    # Mainline uniqueness counts raw B-level candidates only; the A-level
    # interview mainline is the confirmed baseline answer, not a competing draft.
    mainline_count = sum(1 for _name, line in slot_bullets["mainline"] if line.startswith("- **候选"))
    mainline_unique = mainline_count <= 1

    metrics: dict[str, dict[str, object]] = {
        "coverage": {
            "value": coverage, "threshold": th["coverage"], "passed": coverage >= th["coverage"],
            "detail": f"已覆盖 {sum(filled.values())}/6 个槽位" + (f"；缺：{', '.join(missing_slots)}" if missing_slots else ""),
        },
        "answerable_questions": {
            "value": answerable, "threshold": th["answerable_questions"],
            "passed": answerable >= th["answerable_questions"],
            "detail": f"三问可答 {len(answered)}/3" + (f"；未答：{', '.join(q for q in ANSWERABLE_QUESTIONS if q not in answered)}" if len(answered) < 3 else ""),
        },
        "citation_accuracy": {
            "value": accuracy, "threshold": th["citation_accuracy"],
            "passed": accuracy >= th["citation_accuracy"],
            "detail": f"引用 {len(checked) - len(unresolved)}/{len(checked)} 可追溯；噪声率 {noise_rate:.2f}"
                      + (f"；不可追溯：{'; '.join(unresolved[:3])}" if unresolved else ""),
        },
        "mainline_unique": {
            "value": 1.0 if mainline_unique else 0.0, "threshold": th["mainline_unique"],
            "passed": mainline_unique,
            "detail": f"主线候选 {mainline_count} 条" + ("（唯一）" if mainline_unique else "（超过 1 条，其余应进历史区）"),
        },
    }
    overall = all(bool(m["passed"]) for m in metrics.values())
    return {
        "metrics": metrics,
        "overall_passed": overall,
        "counts": {slot: len(bullets) for slot, bullets in slot_bullets.items()},
        "missing_slots": missing_slots,
        "unresolved": unresolved,
    }


def format_scorecard(card: dict[str, object]) -> list[str]:
    """Render the scorecard as human-readable diagnostics with per-metric PASS/FAIL."""
    lines = ["SCORECARD:"]
    metrics = card["metrics"]
    order = ["coverage", "answerable_questions", "citation_accuracy", "mainline_unique"]
    for name in order:
        m = metrics[name]
        verdict = "PASS" if m["passed"] else "FAIL"
        value = m["value"]
        threshold = m["threshold"]
        shown = f"{value:.2f}" if isinstance(value, float) else str(value)
        lines.append(f"- [{verdict}] {name}: {shown} ≥ {threshold:.2f} — {m['detail']}")
    lines.append("SCORECARD_OK" if card["overall_passed"] else "SCORECARD_FAIL: 见上方未达标指标；阈值见 docs/scorecard.md，可由用户裁定调整。")
    return lines

def audit_semantics(target_dir: pathlib.Path) -> list[SemanticFinding]:
    """Read-only semantic audit: structure can pass while semantics are empty/weak.

    Findings are advisory by design (P0-spec P0-B): they never flip the structural
    ``passed`` flag, but they are printed explicitly so ``VALIDATE_OK`` cannot
    hide an empty or padded dossier.
    """
    findings: list[SemanticFinding] = []

    f01 = find_kit_file(target_dir, "01-身份与当前主线.md")
    if f01 is not None:
        lines = f01.read_text(encoding="utf-8", errors="replace").splitlines()
        mainline = _section_lines(lines, "当前主线候选")
        for lineno, _line in mainline[1:]:
            findings.append(SemanticFinding(
                "SEMANTIC_MAINLINE_MULTIPLE", f01.name, lineno,
                "当前主线候选超过 1 条；其余方向应进入独立「历史项目」区，会话标题不得冒充主线",
            ))

    f02 = find_kit_file(target_dir, "02-核心判断准则.md")
    if f02 is not None:
        lines = f02.read_text(encoding="utf-8", errors="replace").splitlines()
        sourced = [ln for ln, l in enumerate(lines, 1) if l.startswith("- **候选") and "原文" in l]
        for lineno, line in enumerate(lines, 1):
            if PRINCIPLE_PADDING_RE.search(line):
                findings.append(SemanticFinding(
                    "SEMANTIC_PRINCIPLE_PADDING", f02.name, lineno,
                    "02 用机器归纳句充数；没有本人原话时应显式写「需访谈」，不拿归纳句填空",
                ))
        has_honest_note = any(("需访谈" in l or "样本不足" in l) for l in lines)
        if not sourced and not has_honest_note:
            findings.append(SemanticFinding(
                "SEMANTIC_PRINCIPLE_EMPTY", f02.name, 1,
                "02 既无带原文/出处的判断句，也没有「需访谈」说明",
            ))

    f03 = find_kit_file(target_dir, "03-硬规则与表达黑话.md")
    if f03 is not None:
        lines = f03.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno, line in _section_lines(lines, "硬规则"):
            ok, reason = rule_shape(line)
            if not ok:
                findings.append(SemanticFinding(
                    "SEMANTIC_RULE_NONRULE", f03.name, lineno,
                    f"规则候选不像持久硬规则（{reason}）：技术摘录 / 单次任务指令 / 对话句应过滤",
                ))

    f04 = find_kit_file(target_dir, "04-正反例避坑账.md")
    if f04 is not None:
        lines = f04.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno, line in _section_lines(lines, "标本"):
            ok, reason = case_shape(line)
            if not ok:
                findings.append(SemanticFinding(
                    "SEMANTIC_CASE_REQUEST", f04.name, lineno,
                    f"正反例不像带场景/损失后果的陈述句（{reason}）：请求句、问句、对话指责应过滤",
                ))

    # Issue #94: advisory scan across identity / principle / rule candidates.
    for fkey, label in (("01-身份与当前主线.md", "身份/主线"), ("02-核心判断准则.md", "准则"),
                          ("03-硬规则与表达黑话.md", "规则")):
        fdoc = find_kit_file(target_dir, fkey)
        if fdoc is None:
            continue
        dlines = fdoc.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno, line in enumerate(dlines, start=1):
            if not line.startswith("- **候选"):
                continue
            if QUESTION_ANY_RE.search(line) or QUESTION_END_RE.search(line):
                findings.append(SemanticFinding(
                    "SEMANTIC_QUESTION_CANDIDATE", fdoc.name, lineno,
                    f"{label}候选看起来是提问句，不应作为本人自述；交付前人工复核剔除"))
            if any(tok in line for tok in PASTED_MATERIAL_TOKENS):
                findings.append(SemanticFinding(
                    "SEMANTIC_PASTED_MATERIAL", fdoc.name, lineno,
                    f"{label}候选疑似粘贴的他人简介/引用材料，不是本人自述；交付前人工复核剔除"))
    return findings


def _scan_pending_markers(text: str) -> tuple[int, list[int], set[int], list[int]]:
    """Return (compliant_count, bare_line_numbers, pending_line_numbers, compliant_lines).

    Lines inside fenced code blocks and inline backtick spans are ignored (case C),
    matching the previous `` `[待确认]` `` meta-rule exemption. The pending line
    numbers let the caller exempt marker shape lines from the placeholder check.
    """
    compliant = 0
    bare_lines: list[int] = []
    pending_lines: set[int] = set()
    compliant_lines: list[int] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scan_line = INLINE_CODE_RE.sub("", line)
        if PENDING_TOKEN not in scan_line:
            continue
        pending_lines.add(lineno)
        if HAS_QUOTE_RE.search(scan_line) and HAS_SOURCE_RE.search(scan_line):
            compliant += 1
            compliant_lines.append(lineno)
        else:
            bare_lines.append(lineno)
    return compliant, bare_lines, pending_lines, compliant_lines


def _scan_uncertain_semantics(text: str) -> list[int]:
    """Return line numbers with natural-language uncertainty but no marker.

    A line that already carries `[待确认]` is handled by the tri-state scanner;
    the same claim must not be reported twice. Inline code / fences are ignored
    so documentation examples do not fail a real kit.
    """
    hits: list[int] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scan_line = INLINE_CODE_RE.sub("", line)
        if PENDING_TOKEN in scan_line:
            continue
        # NFKC folds full-width forms; removing whitespace catches "待 核 实".
        compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", scan_line))
        if "不确定度" in compact:
            # "保留不确定度词" is a rule about epistemic language, not a claim.
            continue
        if UNCERTAIN_SEMANTIC_RE.search(compact):
            hits.append(lineno)
    return hits


def _quote_from_marker(line: str) -> str:
    m = QUOTE_TEXT_RE.search(line)
    if not m:
        return ""
    return next((v for v in m.groupdict().values() if v), "").strip()


def _verify_pending_source(
    line: str,
    kit_dir: pathlib.Path,
    source_roots: list[pathlib.Path] | None = None,
) -> str:
    """Return "" when the marker's source is verifiable, else a reason code.

    Issue #15: previously only the literal words 原文/出处 were checked, so a
    fabricated `出处：fake.md:999` passed. Now a local source must exist, the line
    number must be in range, and the quoted text must appear near that line.
    URLs are accepted as external references (clickable) but not fetched here.
    Template shapes such as `<file>:<line>` stay exempt: they are documentation,
    not a claim about a real file.
    """
    m = SOURCE_REF_RE.search(line)
    if not m:
        return "PENDING_SOURCE_MISSING"
    src = m.group("src").strip().strip("`'\"“”「」[]() ")
    if not src:
        return "PENDING_SOURCE_MISSING"
    if src.startswith("<") or "<file>" in src:
        return ""
    if src.startswith(("http://", "https://")):
        return ""
    line_no: int | None = None
    path_part = src
    sm = SOURCE_LINE_RE.match(src)
    if sm:
        path_part = sm.group("path").strip()
        line_no = int(sm.group("line"))
    # Security: an explicit source must stay inside the kit dir or one of the
    # caller-approved --source-root dirs. Reject absolute paths, drive letters,
    # leading separators and `..` before touching the filesystem.
    if _ABS_REF_RE.match(path_part) or ".." in pathlib.PurePath(path_part).parts:
        return "PENDING_SOURCE_TRAVERSAL"
    roots = [kit_dir, *(source_roots or [])]
    target: pathlib.Path | None = None
    for root in roots:
        root_resolved = root.resolve()
        candidate = (root_resolved / path_part).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError:
            return "PENDING_SOURCE_TRAVERSAL"
        if candidate.is_file():
            target = candidate
            break
    if target is None:
        return "PENDING_SOURCE_MISSING"
    if line_no is not None:
        rows = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if line_no < 1 or line_no > len(rows):
            return "PENDING_SOURCE_LINE_OUT_OF_RANGE"
        quote = _quote_from_marker(line)
        if quote:
            # Allow ±1 line because exported chat files may put the same quote on
            # the adjacent line after a role/time prefix.
            window = "\n".join(rows[max(0, line_no - 2): min(len(rows), line_no + 1)])
            norm_quote = re.sub(r"\s+", "", unicodedata.normalize("NFKC", quote))
            norm_window = re.sub(r"\s+", "", unicodedata.normalize("NFKC", window))
            if norm_quote not in norm_window:
                return "PENDING_SOURCE_QUOTE_MISMATCH"
    return ""


def validate_kit(
    target_dir: pathlib.Path,
    strict: bool = False,
    forbidden_terms: list[str] | None = None,
    source_roots: list[pathlib.Path] | None = None,
    scorecard: bool = True,
    enforce_score: bool = False,
) -> tuple[bool, list[str]]:
    """Return (passed, diagnostics) checking all 6 kit files under target_dir."""
    diagnostics: list[str] = []
    if not target_dir.is_dir():
        return False, [f"Target directory missing: {target_dir}"]

    passed = True
    compliant_total = 0

    for canonical in REQUIRED_KIT_FILES:
        fpath = find_kit_file(target_dir, canonical)
        if fpath is None:
            diagnostics.append(f"MISSING required file: {canonical}")
            passed = False
            continue
        fname = fpath.name
        text = fpath.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) < 80:
            diagnostics.append(f"TOO_SHORT (<80 chars): {fname} ({len(text)} chars)")
            passed = False

        for line in text.splitlines():
            for cliche in AI_CLICHES:
                if cliche in line and not _is_quoted_rule_example(line, cliche):
                    diagnostics.append(f"CLICHE found in {fname}: '{cliche}'")
                    passed = False

        invalid_dates = _invalid_calendar_dates(text)
        if invalid_dates:
            diagnostics.append(f"INVALID_DATE found in {fname}: {invalid_dates[:3]}")
            passed = False

        leaked_paths = SENSITIVE_PATH_RE.findall(text)
        if leaked_paths:
            diagnostics.append(f"PII_OR_SECRET_RISK found in {fname}: {leaked_paths[:2]}")
            passed = False

        if forbidden_terms:
            for term in forbidden_terms:
                if term and term in text:
                    diagnostics.append(f"FORBIDDEN_PII_TERM '{term}' found in {fname}")
                    passed = False

        # `[待确认]` tri-state (CONFLICT-05): A compliant -> INFO; B bare -> fail;
        # C backtick/fence meta reference -> ignored by _scan_pending_markers.
        compliant, bare_lines, pending_lines, compliant_lines = _scan_pending_markers(text)
        for lineno in compliant_lines:
            raw_line = text.splitlines()[lineno - 1]
            reason = _verify_pending_source(raw_line, target_dir, source_roots)
            if reason:
                diagnostics.append(f"{reason}: {fname}:{lineno}")
                passed = False
                compliant_total -= 1
        compliant_total += compliant
        for lineno in bare_lines:
            diagnostics.append(f"PENDING_UNTRACEABLE: {fname}:{lineno}")
            if strict:
                passed = False

        # Issue #2 Bug C: a claim written as "记不清 / 待核实 / 说不准" without a
        # [待确认] marker is still unresolved. Fail in both modes so it cannot
        # slip through as a finished fact.
        for lineno in _scan_uncertain_semantics(text):
            diagnostics.append(f"UNCERTAIN_SEMANTIC: {fname}:{lineno} (转成 [待确认] 并补原文/出处)")
            passed = False

        # Pending marker shape lines are exempt from the placeholder check: the
        # documented shape uses `<疑点>` / `<file>:<line>`, which PLACEHOLDER_RE
        # would otherwise flag as unfilled on an otherwise compliant marker.
        placeholders: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno in pending_lines:
                continue
            placeholders.extend(PLACEHOLDER_RE.findall(RUNTIME_VAR_RE.sub("", line)))
        if strict and placeholders:
            diagnostics.append(f"UNFILLED placeholders in {fname}: {placeholders[:5]}")
            passed = False

    if compliant_total > 0:
        diagnostics.append(
            f"INFO: {compliant_total} compliant '[待确认]' marker(s) pending backfill confirmation."
        )

    # Issue #56: advisory semantic channel. Structural pass/fail stays untouched;
    # empty/padded sections are called out explicitly instead of hidden by VALIDATE_OK.
    semantic = audit_semantics(target_dir)
    for finding in semantic:
        diagnostics.append(
            f"SEMANTIC: [{finding.code}] {finding.file}:{finding.line} {finding.message}"
        )
    if semantic:
        diagnostics.append(
            f"SEMANTIC_REVIEW: {len(semantic)} 条语义提示；结构合格 ≠ 语义合格，"
            "交付前必须处理或显式标「需访谈」。"
        )
    else:
        diagnostics.append("SEMANTIC_OK: 六条语义抽查项通过。")

    # Issue #96: decidable scorecard. Advisory by default; `enforce_score` flips
    # the structural pass when a threshold is missed, and names what is missing.
    if scorecard:
        card = score_kit(target_dir, source_roots)
        diagnostics.extend(format_scorecard(card))
        if enforce_score and not card["overall_passed"]:
            passed = False

    return passed, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the 6-file AI onboarding kit.")
    parser.add_argument("--target", required=True, type=pathlib.Path, help="Directory holding the 6 kit files")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on template placeholders or bare/untraceable [待确认]; compliant markers stay INFO",
    )
    parser.add_argument("--forbidden", nargs="*", default=[], help="Extra personal terms that must not appear")
    parser.add_argument(
        "--source-root",
        action="append",
        default=[],
        type=pathlib.Path,
        help="额外目录：解析 [待确认] 的 出处：<file>:<line>（可多次传入）",
    )
    parser.add_argument("--no-scorecard", action="store_true", help="skip the issue #96 scorecard")
    parser.add_argument("--enforce-score", action="store_true",
                        help="flip PASS to FAIL when a scorecard threshold is missed")
    args = parser.parse_args()

    ok, msgs = validate_kit(
        args.target,
        strict=args.strict,
        forbidden_terms=args.forbidden,
        source_roots=args.source_root,
        scorecard=not args.no_scorecard,
        enforce_score=args.enforce_score,
    )
    for m in msgs:
        print(m)
    if not ok and any(m.startswith("UNFILLED") for m in msgs):
        print(
            "NOTE: 以上 UNFILLED 占位符来自「还没填的空白模板」，不是安装失败。"
            "下一步：把聊天记录放进 work/raw 跑 build，或先完成 6 轮访谈填完模板，再重跑本校验；"
            "语义提示同理，按「需访谈」处理或补原话。"
        )
    print("VALIDATE_OK" if ok else "VALIDATE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
