#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.5 interview source loader (E3-T1 / issue #88, E3-T2 / issue #89).

The 6-stage interview answers used to land in ``work/interview/`` but no
downstream script consumed them. This module turns ``answers.md`` and
``stage-*.md`` (legacy ``round-*.md`` also accepted) into structured **A-level
facts**, each carrying the exact
source file and line so a kit bullet can be traced back to the interview.

Priority rule (implemented here and documented in docs/adr/0002):

- **A 级 · 访谈**：本人在访谈里明确点头确认的答案，是基准；raw 回填不得覆盖。
- **B 级 · raw 回填**：从聊天记录机器抽出的候选，只作补证。
- **C 级 · L2 待确认**：二层回流候选，未签字不生效。

When a raw candidate and an interview fact occupy the same slot but do not
agree, the raw candidate must be downgraded with an explicit ``[待确认]``
marker; the interview fact is never silently overwritten.

Pure standard library; no third-party dependency.
"""

from __future__ import annotations

import pathlib
import re
import unicodedata
from dataclasses import dataclass, field

# Slot keys and the Chinese labels they may appear under in the interview
# markdown. Order matters: a label is matched by prefix containment.
SLOT_LABELS: dict[str, tuple[str, ...]] = {
    "name": ("称呼",),
    "identity": ("身份", "阶段", "现实约束", "硬约束"),
    "mainline": ("当前项目", "当前主线", "长期主线", "当前任务", "核心任务", "主线", "核心项目"),
    "time_boundary": ("时间", "时段"),
    "platform": ("平台",),
    "knowledge_base": ("知识库",),
    "principle": ("判断准则", "准则", "优先顺序", "验收标准", "刹车规矩"),
    "rule": ("红线", "硬规则", "规则", "越界", "操作规范"),
    "positive": ("正例", "正面案例", "有效做法"),
    "negative": ("反例", "反面案例", "踩坑"),
}

SLOT_HEADING: dict[str, str] = {
    "name": "称呼",
    "identity": "身份/阶段",
    "mainline": "当前主线",
    "time_boundary": "时间边界",
    "platform": "常用平台",
    "knowledge_base": "知识库",
    "principle": "判断准则",
    "rule": "硬规则",
    "positive": "正例",
    "negative": "反例",
}

RULE_VERB_RE = re.compile(r"(确认|同意|不要|禁止|不许|必须|绝不|删|改|红线|规则|底线|只读|换方案|不代签|不伪造)")
PRINCIPLE_CODE_RE = re.compile(r"^\s*(?P<code>\d[A-Z])\s*[（(](?P<text>.+)[）)]\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s*(?:\*\*|__)?(?P<label>[^：:*_]+)(?:\*\*|__)?\s*[：:]\s*(?P<value>.+)$")
NUMBERED_RE = re.compile(r"^\s*\d+[.、)）]\s*(?:\*\*|__)?(?P<label>[^：:*_]+)(?:\*\*|__)?\s*[：:]\s*(?P<value>.+)$")
PLAIN_NUMBERED_RE = re.compile(r"^\s*\d+[.、)）]\s*(?P<value>.+)$")
PLAIN_BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<value>.+)$")
OPTION_RE = re.compile(r"^\s*[-*]\s*(?P<letter>[A-F])(?:[.、:：\s]+)(?P<value>.+)$")
ANSWER_LINE_RE = re.compile(
    r"^(?:AI\s*预填|预填|用户确认|确认答案|本人确认|最终确认|回答|答案|选择)\s*[：:]\s*(?P<rest>.*)$"
)
ROUND_FILE_RE = re.compile(r"(?:round|stage)[-\s]?(\d+)\.md$", re.IGNORECASE)

# Clauses that are product complaints about the interviewer itself, not
# durable facts about the user. They must not be lifted into the kit.
META_COMPLAINT_MARKERS = ("模板化", "语音误写", "待补充", "问题是",
                          "我觉得这里", "有点奇怪", "issue", "Issue", "用户指出",
                          "阶段目标", "产品问题", "问题模板", "重问", "疑为", "澄清",
                          "复述确认", "用户提出的")

# Labels that describe the interview process / product feedback, not a durable
# fact about the user. They must not be lifted into a dossier slot.
META_LABELS = ("阶段目标", "用户提出", "产品问题", "澄清", "复述确认", "深钩", "深钩/正反例", "卡点", "证据", "状态", "规则")

# Section headings that explain how to use the interview sheet rather than
# holding durable personal facts.
IGNORE_SECTION_MARKERS = ("怎么用", "使用说明", "如何使用", "填写说明", "操作指南")
HOLLOW_OPTION_MARKERS = (
    "暂时没有", "其他硬限制", "自定义", "全打字", "有（列", "有(列",
    "有，先全记", "有,先全记", "都清晰", "不急着写",
    "其他特定禁令", "其他禁令", "其他补充", "其他项",
)
_QUOTE_PATH_RE = re.compile(r"(?:[A-Za-z]:\\Users\\[^\s，。；、）】]+|/Users/[^\s，。；、）】]+|/home/[^\s，。；、）】]+)")
_QUOTE_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_QUOTE_ID_RE = re.compile(r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
_PENDING_TAG_RE = re.compile(r"`?\[待确认\]`?")
_UNCERTAIN_SAFE = (
    "记不清", "记不得", "记不住", "记混", "待核实", "待人工核实", "未核实",
    "说不准", "拿不准", "没印象", "想不起来", "可能记错", "可能记混",
    "我不确定", "我拿不准",
)


def _normalize(text: str) -> str:
    compact = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[\s，。；、：:（）()「」『』/／·\-_]", "", compact)


def _split_clauses(value: str) -> list[str]:
    return [c.strip(" ；;。.，,") for c in re.split(r"[；;]", value) if c.strip(" ；;。.")]


@dataclass
class InterviewFact:
    """One A-level fact confirmed in the interview, with provenance."""

    slot: str
    text: str
    source_file: str
    source_line: int
    quote: str
    code: str = ""
    level: str = "A"
    channel: str = "访谈"
    evidence_line: int = 0

    def evidence_bullet(self, evidence_line: int) -> str:
        """Render the kit bullet for this fact. ``evidence_line`` points into
        the copied interview digest stored next to the kit."""
        head = SLOT_HEADING.get(self.slot, self.slot)
        code = f" {self.code}" if self.code else ""
        return (
            f"- **A级·访谈{code}** {head}：{self.text} ｜ "
            f"原文：「{self.quote}」 ｜ 出处：_evidence/interview-lines.md:{evidence_line} ｜ "
            f"来源：{self.source_file}:{self.source_line}"
        )


@dataclass
class InterviewBundle:
    facts: list[InterviewFact] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)

    def by_slot(self, slot: str) -> list[InterviewFact]:
        return [f for f in self.facts if f.slot == slot]

    def get(self, slot: str) -> InterviewFact | None:
        return next((f for f in self.facts if f.slot == slot), None)

    def normalized_slot_text(self, slot: str) -> set[str]:
        return {_normalize(f.text) for f in self.by_slot(slot)}

    def is_empty(self) -> bool:
        return not self.facts


def _classify_label(label: str) -> str | None:
    label = label.strip()
    for slot, labels in SLOT_LABELS.items():
        if any(lab in label for lab in labels):
            return slot
    return None


def _sanitize_quote(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    t = _QUOTE_PATH_RE.sub("（本地路径）", t)
    t = _QUOTE_PHONE_RE.sub("（手机号）", t)
    t = _QUOTE_ID_RE.sub("（证件号）", t)
    for word in _UNCERTAIN_SAFE:
        t = t.replace(word, "未定")
    t = t.replace("[待确认]", "（待确认）")
    t = t.replace("<", "").replace(">", "")
    t = t.replace("｜", " | ").replace("「", "『").replace("」", "』")
    return t[:260]


def _clean_display(text: str) -> str:
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = _PENDING_TAG_RE.sub("", t)
    t = t.replace("`", "")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([，。；、：！？])", r"\1", t)
    for word in _UNCERTAIN_SAFE:
        t = t.replace(word, "未定")
    t = t.replace("<", "").replace(">", "")
    t = t.replace("｜", " | ").replace("「", "『").replace("」", "』")
    return t.strip("。；;，, ")


def _clean_fact_text(slot: str, text: str) -> str:
    """Drop coverage/parenthetical notes that are not the fact itself."""
    t = _clean_display(text)
    if slot == "name":
        t = re.sub(r"[（(].*?[)）]", "", t).strip()
        m = re.search(r"[「『“\"]([^」』”\"]+)[」』”\"]", t)
        if m:
            t = m.group(1)
        else:
            t = re.sub(r"^(?:统一)?称呼[：:\s]*", "", t).strip()
    # Plain principle clauses may keep a stray option letter: "A（目标与真需求优先）".
    t = re.sub(r"^\s*\d?[A-Z]\s*[（(]", "", t)
    t = re.sub(r"[）)]\s*$", "", t).strip()
    t = t.rstrip("。；;，, ")
    return t


def _infer_section_slot(heading: str) -> str | None:
    if any(mark in heading for mark in IGNORE_SECTION_MARKERS):
        return "__IGNORE__"
    if "02-" in heading or "核心判断" in heading or "判断准则" in heading or "判断与验收" in heading:
        return "principle"
    if "03-" in heading or "硬规则" in heading or "红线" in heading:
        return "rule"
    if "04-" in heading or "正例与反例" in heading or "避坑" in heading or "反面案例" in heading:
        return "case"
    if "01-" in heading or "当前项目" in heading or "身份与当前主线" in heading:
        return "mainline"
    if "00-" in heading or "多平台" in heading or "知识库" in heading:
        return "platform"
    if "AGENTS" in heading or "人设与表达" in heading:
        return "rule"
    return None


def _infer_question_slot(q_heading: str, section_slot: str | None) -> str | None:
    if section_slot == "__IGNORE__":
        return None
    # Skip meta questions about uncertain recall or voice typos.
    if any(k in q_heading for k in ("记不清", "语音输入", "转写错词", "还有没有", "疑点")):
        return None
    if any(k in q_heading for k in ("称呼", "别名", "网名")):
        return "name"
    if any(k in q_heading for k in ("彻底放弃", "放弃", "反例", "踩坑", "拦停", "哪 1–2 个坑", "哪个坑", "哪些坑")):
        return "negative"
    if any(k in q_heading for k in ("正例", "永远固化", "有效做法")):
        return "positive"
    if any(k in q_heading for k in ("核心项目", "当前项目", "主线")):
        return "mainline"
    if any(k in q_heading for k in ("硬约束", "时间/阶段", "阶段", "身份")):
        return "identity"
    if any(k in q_heading for k in ("时间", "时段")):
        return "time_boundary"
    if any(k in q_heading for k in ("知识库", "笔记")):
        return "knowledge_base"
    if any(k in q_heading for k in ("平台", "AI 端")):
        return "platform"
    if any(k in q_heading for k in ("优先顺序", "验收", "刹车", "判断", "准则", "裁决")):
        return "principle"
    if any(k in q_heading for k in ("不能碰", "红线", "硬规则", "反感", "越界", "分歧", "站位", "表达顺序", "操作")):
        return "rule"
    if section_slot and section_slot != "case":
        return section_slot
    return None


def _extract_option_letters(rest: str, options: dict[str, tuple[int, str, str]]) -> list[str]:
    cleaned = _PENDING_TAG_RE.sub("", rest).strip()
    if not cleaned:
        return []
    # Drop parenthetical uncertain/auxiliary option notes such as "（A 待确认）",
    # "（不确定项加 C）", or "（B 作为补充）" before scanning primary option letters.
    no_aux_paren = re.sub(
        r"[（(][^）)]*(?:待确认|不确定|作为补充|补充|可选)[^）)]*[）)]",
        "",
        cleaned,
    )
    if not re.match(r"^[A-F](?:[\s+/、，,（(全]|$)", no_aux_paren):
        return []
    letters: list[str] = []
    for ch in re.findall(r"(?<![A-Za-z])([A-F])(?![A-Za-z])", no_aux_paren):
        if ch in options and ch not in letters:
            letters.append(ch)
    return letters


def _bigrams(text: str) -> set[str]:
    norm = _normalize(text)
    return {norm[i:i + 2] for i in range(len(norm) - 1) if len(norm[i:i + 2]) == 2}


def _parse_value(slot: str, value: str, source_file: str, line: int,
                 quote: str) -> list[InterviewFact]:
    value = value.strip()
    if not value or value in ("[待确认]", "待确认"):
        return []
    facts: list[InterviewFact] = []
    if slot in ("principle",):
        # `1A（目标与真需求优先）/ 2C（内外双验收）/ 3B（...）`
        for clause in re.split(r"/", value):
            clause = clause.strip()
            if not clause:
                continue
            m = PRINCIPLE_CODE_RE.match(clause)
            if m:
                facts.append(InterviewFact(
                    slot=slot, text=m.group("text"), source_file=source_file,
                    source_line=line, quote=quote, code=m.group("code")))
            else:
                facts.append(InterviewFact(
                    slot=slot, text=_clean_fact_text(slot, clause), source_file=source_file,
                    source_line=line, quote=quote))
    elif slot in ("rule", "positive", "negative"):
        for clause in _split_clauses(value):
            clause = _clean_fact_text(slot, clause)
            if slot == "rule" and not RULE_VERB_RE.search(clause) and "批准" not in clause:
                continue  # bare topic tag, not a standing rule
            facts.append(InterviewFact(
                slot=slot, text=clause, source_file=source_file,
                source_line=line, quote=quote))
    else:
        facts.append(InterviewFact(
            slot=slot, text=_clean_fact_text(slot, value), source_file=source_file,
            source_line=line, quote=quote))
    return facts


def _parse_markdown(path: pathlib.Path, bundle: InterviewBundle) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    source_file = path.name
    seen: set[str] = set()

    def _add(fact: InterviewFact) -> None:
        fact.text = _clean_display(fact.text)
        fact.quote = _sanitize_quote(fact.quote)
        if not fact.text or len(fact.text) < 2:
            return
        key = f"{fact.slot}|{_normalize(fact.text)}"
        if key in seen:
            return
        # Weak overlap dedup: a round note restating the same summary answer
        # must not appear twice in the same slot. Two facts overlap when they
        # share at least two CJK bigrams; one shared bigram (e.g. 不要) is not
        # enough to merge two distinct rules.
        new_grams = _bigrams(fact.text)
        for existing in bundle.facts:
            if existing.slot != fact.slot:
                continue
            shared = new_grams & _bigrams(existing.text)
            if len(shared) >= 2:
                return
        seen.add(key)
        bundle.facts.append(fact)

    # Pass 1: standard `answers.md` / `stage-N.md` / `round-N.md` key-value lines.
    in_ignored_section = False
    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if line.startswith("## "):
            in_ignored_section = _infer_section_slot(line) == "__IGNORE__"
            continue
        if in_ignored_section:
            continue
        m = BULLET_RE.match(line) or NUMBERED_RE.match(line)
        if not m:
            continue
        label, value = m.group("label").strip(), m.group("value").strip()
        if any(meta in label for meta in META_LABELS):
            continue
        slot = _classify_label(label)
        if slot is None:
            continue
        # Skip meta complaints recorded in the interview itself.
        if any(marker in line for marker in META_COMPLAINT_MARKERS):
            continue
        for fact in _parse_value(slot, value, source_file, lineno, line):
            _add(fact)

    # Pass 2: structured prefill-card & section-aware Markdown parsing
    # (## Round -> ### Q -> - A/- B options -> **AI 预填：...** / multi-line blocks,
    # and section-level numbered items under e.g. `## 先复述：...核心判断`).
    section_slot: str | None = None
    q_heading = ""
    q_slot: str | None = None
    options: dict[str, tuple[int, str, str]] = {}
    in_answer_block = False
    answer_block_slot: str | None = None

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line == "---":
            in_answer_block = False
            continue
        if line.startswith("## "):
            section_slot = _infer_section_slot(line)
            q_heading = ""
            q_slot = None
            options = {}
            in_answer_block = False
            continue
        if section_slot == "__IGNORE__":
            continue
        if line.startswith("### "):
            q_heading = line[4:].strip()
            q_slot = _infer_question_slot(q_heading, section_slot)
            options = {}
            in_answer_block = False
            continue
        if line.startswith(("证据：", "证据:", "> ", "**本轮", "本轮")):
            in_answer_block = False
            continue

        # Collect multi-line block items right after `**AI 预填：**`
        if in_answer_block:
            kv = BULLET_RE.match(line) or NUMBERED_RE.match(line)
            if kv:
                lbl = kv.group("label").strip()
                val = kv.group("value").strip()
                if any(meta in lbl for meta in META_LABELS):
                    continue
                item_slot = _classify_label(lbl) or answer_block_slot
                if item_slot and item_slot != "case":
                    for fact in _parse_value(item_slot, val, source_file, lineno, line):
                        _add(fact)
                continue
            plain_item = PLAIN_NUMBERED_RE.match(line) or PLAIN_BULLET_RE.match(line)
            if plain_item and answer_block_slot and answer_block_slot != "case":
                val = _clean_display(plain_item.group("value"))
                if val and not any(h in val for h in HOLLOW_OPTION_MARKERS):
                    _add(InterviewFact(
                        slot=answer_block_slot, text=val, source_file=source_file,
                        source_line=lineno, quote=line))
                continue
            in_answer_block = False

        # Section-level numbered items (e.g. `## 先复述：我目前读到的核心判断`)
        if not q_heading and section_slot and section_slot not in ("__IGNORE__", "case"):
            pm = PLAIN_NUMBERED_RE.match(line)
            if pm and not any(marker in line for marker in META_COMPLAINT_MARKERS):
                val = _clean_display(pm.group("value"))
                if val and len(val) >= 6:
                    _add(InterviewFact(
                        slot=section_slot, text=val, source_file=source_file,
                        source_line=lineno, quote=line))
            continue

        # Inside a `### Q...` block: capture option lines `- A ...`, `- B ...`
        if q_heading:
            om = OPTION_RE.match(line)
            if om:
                letter = om.group("letter").upper()
                options[letter] = (lineno, om.group("value").strip(), line)
                continue

            plain_line = re.sub(r"\*\*(.+?)\*\*", r"\1", line).strip()
            am = ANSWER_LINE_RE.match(plain_line)
            if am and q_slot:
                rest_raw = am.group("rest").strip()
                rest_clean = _PENDING_TAG_RE.sub("", rest_raw).strip()
                if not rest_clean:
                    in_answer_block = True
                    answer_block_slot = q_slot
                    continue
                letters = _extract_option_letters(rest_raw, options)
                if letters:
                    # Extract optional inline supplement like `（不代签字、不伪造）`,
                    # skipping option cross-references such as `（B 作为补充）` or `（不确定项加 C）`.
                    extra_notes: list[str] = []
                    for pm_note in re.findall(r"[（(]([^）)]+)[）)]", rest_clean):
                        if any(k in pm_note for k in ("待确认", "主线", "推荐")):
                            continue
                        if re.search(r"(?<![A-Za-z])[A-F](?![A-Za-z])", pm_note):
                            continue
                        if len(pm_note.strip()) >= 4:
                            extra_notes.append(pm_note.strip())
                    is_neg_q = any(k in q_heading for k in ("反感", "越界", "不能碰", "禁止"))
                    for letter in letters:
                        opt_line, opt_val, opt_raw = options[letter]
                        opt_clean = _clean_display(opt_val)
                        if not opt_clean or any(h in opt_clean for h in HOLLOW_OPTION_MARKERS):
                            continue
                        if q_slot == "rule" and is_neg_q and not re.match(r"^(?:禁止|严禁|不要|不许|绝不)", opt_clean):
                            opt_clean = f"禁止：{opt_clean}"
                        _add(InterviewFact(
                            slot=q_slot, text=opt_clean, source_file=source_file,
                            source_line=opt_line, quote=opt_raw))
                    for note in extra_notes:
                        _add(InterviewFact(
                            slot=q_slot, text=note, source_file=source_file,
                            source_line=lineno, quote=line))
                else:
                    if not any(h in rest_clean for h in HOLLOW_OPTION_MARKERS):
                        for fact in _parse_value(q_slot, rest_clean, source_file, lineno, line):
                            _add(fact)

    # Round files also carry rule statements inside free-form "用户原话"
    # bullets (e.g. "操作规范：在动手前要先进行确认…；没有经过本人同意，
    # 不要删文件"). The summary line in answers.md does not repeat them.
    if ROUND_FILE_RE.search(source_file):
        for lineno, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            m = NUMBERED_RE.match(line)
            if not m:
                continue
            value = m.group("value").strip()
            if RULE_VERB_RE.search(value) and not any(
                marker in line for marker in META_COMPLAINT_MARKERS
            ):
                for clause in _split_clauses(value):
                    if RULE_VERB_RE.search(clause):
                        _add(InterviewFact(
                            slot="rule", text=clause, source_file=source_file,
                            source_line=lineno, quote=line))


def load_interview(path: pathlib.Path | str | None) -> InterviewBundle:
    """Load interview answers from a directory or a single answers.md file.

    Accepts:
    - a directory containing ``answers.md`` and/or ``stage-1.md`` … ``stage-6.md``;
      legacy ``round-1.md`` … ``round-6.md`` is also accepted;
    - a single ``answers.md`` (or any ``stage-N.md`` / ``round-N.md``) file.

    Returns an empty bundle when ``path`` is None or missing; callers treat
    that as "no interview input", matching the pre-#88 behaviour.
    """
    bundle = InterviewBundle()
    if path is None:
        return bundle
    root = pathlib.Path(path).expanduser()
    if not root.exists():
        return bundle

    files: list[pathlib.Path] = []
    if root.is_file():
        files = [root]
    else:
        answers = root / "answers.md"
        if answers.is_file():
            files.append(answers)
        stages = sorted(
            (p for p in root.iterdir() if p.is_file() and ROUND_FILE_RE.search(p.name)),
            key=lambda p: int(ROUND_FILE_RE.search(p.name).group(1)),
        )
        files.extend(stages)
        if not files:
            files = sorted(root.glob("*.md"))

    for f in files:
        bundle.source_files.append(f.name)
        _parse_markdown(f, bundle)
    return bundle


def raw_agrees(fact: InterviewFact, raw_text: str) -> bool:
    """Weak overlap check used for conflict marking (issue #89).

    True when a key token of the interview fact also appears in the raw
    candidate. This is deliberately conservative: a false "agree" would hide
    a conflict, so the fallback for thin texts is False (mark it pending).
    """
    norm_raw = _normalize(raw_text)
    if not norm_raw:
        return False
    tokens = [t for t in re.findall(r"[一-鿿]{2,}", _normalize(fact.text)) if len(t) >= 2]
    if not tokens:
        return True  # no Chinese token to compare; do not invent a conflict
    return any(t in norm_raw for t in tokens)
