#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.5 interview source loader (E3-T1 / issue #88, E3-T2 / issue #89).

The 6-round interview answers used to land in ``work/interview/`` but no
downstream script consumed them. This module turns ``answers.md`` and
``round-*.md`` into structured **A-level facts**, each carrying the exact
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
    "identity": ("身份", "阶段"),
    "mainline": ("当前项目", "当前主线", "主线", "核心项目"),
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

RULE_VERB_RE = re.compile(r"(确认|同意|不要|禁止|不许|必须|绝不|删|改|红线|规则|底线)")
PRINCIPLE_CODE_RE = re.compile(r"^\s*(?P<code>\d[A-Z])\s*[（(](?P<text>.+)[）)]\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s*(?P<label>[^：:]+)[：:]\s*(?P<value>.+)$")
NUMBERED_RE = re.compile(r"^\s*\d+[.、)）]\s*(?P<label>[^：:：]+)[：:]\s*(?P<value>.+)$")
ROUND_FILE_RE = re.compile(r"round[-\s]?(\d+)\.md$", re.IGNORECASE)

# Clauses that are product complaints about the interviewer itself, not
# durable facts about the user. They must not be lifted into the kit.
META_COMPLAINT_MARKERS = ("模板化", "预填", "语音误写", "待补充", "待确认", "问题是",
                          "我觉得这里", "有点奇怪", "issue", "Issue", "用户指出",
                          "阶段目标", "产品问题", "问题模板", "重问", "疑为", "澄清",
                          "复述确认", "用户提出的")

# Labels that describe the interview process / product feedback, not a durable
# fact about the user. They must not be lifted into a dossier slot.
META_LABELS = ("阶段目标", "用户提出", "产品问题", "澄清", "复述确认", "深钩", "深钩/正反例")


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


def _clean_fact_text(slot: str, text: str) -> str:
    """Drop coverage/parenthetical notes that are not the fact itself."""
    t = text.strip()
    if slot == "name":
        t = re.sub(r"[（(].*?[)）]", "", t).strip()
        m = re.search(r"「([^」]+)」", t)
        if m:
            t = m.group(1)
    # Plain principle clauses may keep a stray option letter: "A（目标与真需求优先）".
    t = re.sub(r"^\s*\d?[A-Z]\s*[（(]", "", t)
    t = re.sub(r"[）)]\s*$", "", t).strip()
    t = t.rstrip("。；;，, ")
    return t


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

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
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
    - a directory containing ``answers.md`` and/or ``round-1.md`` … ``round-6.md``;
    - a single ``answers.md`` (or any ``round-N.md``) file.

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
        rounds = sorted(
            (p for p in root.glob("round-*.md") if ROUND_FILE_RE.search(p.name)),
            key=lambda p: int(ROUND_FILE_RE.search(p.name).group(1)),
        )
        files.extend(rounds)
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
