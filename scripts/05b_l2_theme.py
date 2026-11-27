#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""L2 theme miner: cross-conversation recurring themes the kit does not cite.

This is the missing *difference* axis of layer-2 backfill. `05_deep_backfill.py`
mines a single record's self-setback cues; this script asks a different question:

    Which durable themes recur across >=2 different conversations, while the
    current six files never cite any of those records?

Design constraints:
- THREE inputs are mandatory: profiles (A), layer-1 report (B), cold DB (C).
- Every output is `[待确认]`; no official body is modified.
- No LLM, no external model download: deterministic cue + sentence rules.
- The selected excerpt is copied verbatim from the DB; secrets are redacted.
- A theme needs >=2 distinct source_file values, not just 2 rows in one chat.
- Contradictory themes are not silently resolved; every item stays needs_llm.

Outputs match `08_l2_apply.py`:
  work/l2_theme/l2_candidates.md
  work/l2_theme/l2_profile_patches/<profile>.patch.md
  work/l2_theme/l2_review.jsonl
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Iterable

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

l2 = importlib.import_module("05_deep_backfill")

SENT_SPLIT_RE = re.compile(r"[。！？!?\n；;]")
SECRET_RE = re.compile(r"(?i)(secretid|secretkey|api[_-]?key|token|password|passwd|sk-)[^，。；\s]{0,40}")
LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{32,}")
QUESTION_RE = re.compile(r"[？?]|是不是|能不能|可不可以|有没有|为什么|怎么|如何|哪些|请问")
AI_DIRECTED_PREFIX = (
    "你可以", "你看", "你帮", "请你", "给我", "帮我", "你先", "你要", "你这里",
    "你那个", "你在", "你按", "你把", "你需要", "你现在", "你觉得", "你进行",
    "你直接", "你继续", "你可以看", "你看一下",
)
META_PREFIX = ("我觉得你可以", "那你看", "你先", "继续开始", "你给我", "我要你")


@dataclass(frozen=True)
class Theme:
    theme_id: str
    signal: str
    target_profile: str
    section_anchor: str
    cues: tuple[str, ...]
    evidence_label: str
    # identity themes need first-person in the excerpt; rule themes may be an
    # imperative sentence ("不要拿总结冒充原文") without a subject.
    require_first_person: bool = True


THEMES: tuple[Theme, ...] = (
    Theme(
        "primary_source", "hard_rule", "03-硬规则与表达黑话.md",
        "## 一、对任何接手 AI 的 11 条硬规则",
        ("一手", "原文", "真实报告", "真实资料", "不是总结", "不要总结", "别总结",
         "自己判断", "真实看", "真实比对"),
        "一手资料/真实比对",
    ),
    Theme(
        "real_delivery", "recurring_mistake", "04-正反例避坑账.md",
        "## 二、反例标本",
        ("成品", "复刻", "只拆解", "不是只拆", "真实做出来", "做出来", "没做出来"),
        "拆解必须落到成品",
    ),
    Theme(
        "local_api", "hard_rule", "03-硬规则与表达黑话.md",
        "## 一、对任何接手 AI 的 11 条硬规则",
        ("本地跑不了", "本地太卡", "太卡", "接 API", "接API", "云端", "不想跑"),
        "本地跑不动就走 API/云端",
        require_first_person=False,
    ),
    Theme(
        "reference_model", "hard_rule", "03-硬规则与表达黑话.md",
        "## 一、对任何接手 AI 的 11 条硬规则",
        ("参考建模", "不是真实建模", "多视图", "独立拆分", "参考而非真实"),
        "3D 资产只做参考建模",
        require_first_person=False,
    ),
    Theme(
        "plain_language", "hard_rule", "03-硬规则与表达黑话.md",
        "## 三、核心黑话与已纠偏词典",
        ("白话", "通俗", "正常说话", "不要跟我说", "黑话", "说人话", "具体怎么做"),
        "解释必须说人话",
        require_first_person=False,
    ),
    Theme(
        "real_project_test", "hard_rule", "03-硬规则与表达黑话.md",
        "## 一、对任何接手 AI 的 11 条硬规则",
        ("真实项目", "真实跑", "跑通", "测试可行", "真实测试"),
        "必须用真实项目验证",
        require_first_person=False,
    ),
)
THEME_BY_ID = {t.theme_id: t for t in THEMES}


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = SECRET_RE.sub("[已脱敏]", text)
    text = LONG_TOKEN_RE.sub("[已脱敏]", text)
    return text


def _sentences(content: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT_RE.split(content) if s.strip()]


def _is_question(s: str) -> bool:
    return bool(QUESTION_RE.search(s))


def _is_ai_directed(s: str) -> bool:
    head = s.strip()[:16]
    if any(head.startswith(p) for p in AI_DIRECTED_PREFIX):
        return True
    if any(s.startswith(p) for p in META_PREFIX):
        return True
    return False


def _has_secret(content: str) -> bool:
    return bool(re.search(r"(?i)(secretid|secretkey|AKID|sk-|api[_-]?key)", content))


# Evidence classes (issue #147): "source files hit" is NOT the same as
# "conversations where the user actually said this". A pasted prompt template
# can mention the same words in six files and still be zero personal evidence.
PROMPT_MARKERS = (
    "字之间", "字左右", "不少于", "不超过", "字数", "输出格式", "格式要求",
    "请以", "请写", "请生成", "角色设定", "扮演", "分点作答", "目录结构",
    "参考文献", "要求如下", "以下要求",
)
# A task brief handed to the AI reads like a spec, not like a person stating a
# standard: second-person directive, section numbering, "要求：", "模块 N".
AI_DIRECTIVE_RE = re.compile(
    r"(^|[，。：；、\s])(你|您)(需要|要|必须|得|应该|可以|不要|不能)"
    r"|你的(最终|产出|任务|回答|输出|报告|方案|具体)"
)
STRUCT_MARK_RE = re.compile(
    r"^(?:\*\*)?(?:[（(][0-9a-z一二三四五六七八九十][）)]|[0-9]+[.、)）]"
    r"|要求：|要求如下|模块\s*[0-9一二三四五六七八九十])"
)
LIST_HEAD_RE = re.compile(r"[：:]\s*1[.、)）]")
FIRST_PERSON = ("我", "本人", "我们")
RULE_WORDS = ("必须", "不要", "禁止", "绝不", "不能", "别")


def classify_evidence(sentence: str) -> str:
    """One of personal_on_topic / prompt_or_external / off_topic.

    Rule-based on purpose: a pasted brief can mention "我" and still be a
    template, so second-person directives, section numbering and formatting
    words are checked before the first-person fallback.
    """
    s = sentence.strip()
    first_person = any(w in s for w in FIRST_PERSON)
    has_rule = any(w in s for w in RULE_WORDS)
    if AI_DIRECTIVE_RE.search(s) or STRUCT_MARK_RE.search(s) or LIST_HEAD_RE.search(s):
        return "prompt_or_external"
    if not first_person and any(m in s for m in PROMPT_MARKERS):
        return "prompt_or_external"
    if _is_question(s) or _is_ai_directed(s):
        return "off_topic"
    if not first_person and not has_rule:
        return "off_topic"
    return "personal_on_topic"



def pick_sentence(theme: Theme, content: str) -> str | None:
    """Return one verbatim sentence carrying the theme cue, or None."""
    content = _clean(content)
    for sentence in _sentences(content):
        if not (15 <= len(sentence) <= 220):
            continue
        if _is_question(sentence) or _is_ai_directed(sentence):
            continue
        if not any(cue in sentence for cue in theme.cues):
            continue
        if theme.require_first_person and not any(p in sentence for p in ("我", "本人", "我们")):
            continue
        # Rule themes: an imperative sentence without "我" is allowed only when
        # it has a rule verb, otherwise it is just a task instruction.
        if not theme.require_first_person and not any(
            p in sentence for p in ("我", "本人", "我们", "必须", "不要", "禁止", "不能", "绝不")
        ):
            continue
        return sentence
    return None


def mine_themes(records: list[dict[str, str]], profiles: dict[str, str],
                first_pass: l2.FirstPassIndex, min_docs: int = 2,
                ) -> tuple[list[l2.L2Candidate], list[dict[str, str]]]:
    coverage = l2.build_coverage_index(profiles)
    candidates: list[l2.L2Candidate] = []
    dropped: list[dict[str, str]] = []
    counter = 1000
    for theme in THEMES:
        hit_rows: list[tuple[dict[str, str], str]] = []
        for r in records:
            if r["role"] != "user":
                continue
            if r["rec_id"] in coverage.covered_rec_ids:
                dropped.append({"rec_id": r["rec_id"], "theme": theme.theme_id,
                                "reason": "C0_covered_by_profile"})
                continue
            if r["rec_id"] in first_pass.pending_rec_ids:
                dropped.append({"rec_id": r["rec_id"], "theme": theme.theme_id,
                                "reason": "C1_cross_ref_L1"})
                continue
            if _has_secret(r["content"]):
                dropped.append({"rec_id": r["rec_id"], "theme": theme.theme_id,
                                "reason": "secret_redacted_record"})
                continue
            sentence = pick_sentence(theme, r["content"])
            if sentence:
                hit_rows.append((r, sentence))
        classified = [(r, sentence, classify_evidence(sentence)) for r, sentence in hit_rows]
        personal_rows = [(r, s) for r, s, label in classified if label == "personal_on_topic"]
        personal_docs = {r["source_file"] for r, _ in personal_rows}
        source_file_hits = {r["source_file"] for r, _, _ in classified}
        class_counts = {
            label: sum(1 for _r, _s, lab in classified if lab == label)
            for label in ("personal_on_topic", "prompt_or_external", "off_topic")
        }
        if len(personal_docs) < min_docs or len(personal_rows) < 2:
            if hit_rows:  # themes with zero hits stay silent, not rejected
                dropped.append({
                "rec_id": personal_rows[0][0]["rec_id"] if personal_rows else "",
                "theme": theme.theme_id,
                "reason": "C2_insufficient_personal_evidence",
                "personal_docs": len(personal_docs),
                "source_file_hits": len(source_file_hits),
                "classified": class_counts,
            })
            continue
        # Best excerpt: shortest sentence with the highest cue count; keeps the
        # candidate readable and avoids pasting a 200-char wall.
        def score(pair: tuple[dict[str, str], str]) -> tuple[int, int]:
            s = pair[1]
            return (sum(1 for c in theme.cues if c in s), -len(s))
        best = sorted(personal_rows, key=score, reverse=True)[0]
        # Evidence list: at most 4 personal records, each with a redacted excerpt.
        evidence_rows = personal_rows[:4]
        evidence = (
            "跨对话复现 personal_docs={} ｜ source_file_hits={} ｜ records={} ｜ 命中={} ｜ "
            "分类 personal={}/prompt_or_external={}/off_topic={}"
        ).format(
            len(personal_docs), len(source_file_hits),
            ",".join(r["rec_id"] for r, _ in evidence_rows),
            theme.evidence_label,
            class_counts["personal_on_topic"], class_counts["prompt_or_external"],
            class_counts["off_topic"],
        )
        counter += 1
        candidates.append(l2.L2Candidate(
            candidate_id=f"L2-{counter:04d}",
            rec_id=best[0]["rec_id"],
            created_at=best[0]["created_at"],
            signal=theme.signal,
            target_profile=theme.target_profile,
            section_anchor=theme.section_anchor,
            evidence=evidence,
            excerpt=_clean(best[1])[:220],
            source_file="; ".join(sorted(personal_docs))[:240],
            cross_ref="none",
            phrase_hits=len(hit_rows),
            needs_llm=True,
        ))
    candidates.sort(key=lambda c: c.candidate_id)
    return candidates, dropped


def render_theme_report(candidates: list[l2.L2Candidate], dropped: list[dict[str, str]]) -> str:
    lines = [
        "# L2 主题差集回流候选报告", "",
        "> ⚠️ **主题层候选 · 全部 [待确认] · 未经本人签字不得写入正式档案。**",
        "> 生成方式：跨对话复现实词/主题簇 → 差集（当前六份未引用）→ 原文摘录；",
        "> 不做语义判决，`needs_llm=true` 必须由本人或独立 AI 双尺复核。", "",
        f"> 共 `{len(candidates)}` 条主题候选。", "",
    ]
    for c in candidates:
        lines.extend([
            f"### {c.candidate_id} [待确认] [{c.rec_id} | {c.created_at}]",
            f"- **信号**：{c.signal} ｜ **建议位置**：{c.target_profile} / {c.section_anchor}",
            f"- **证据**：{c.evidence}",
            f"- **溯源**：`source_file={c.source_file}` ｜ **L1 关系**：{c.cross_ref}",
            f"- **needs_llm**：{str(c.needs_llm).lower()} ｜ **状态**：{c.status}",
            f"- **原文摘录**：> {c.excerpt}",
            "",
        ])
    if dropped:
        rejected = [d for d in dropped if d["reason"] == "C2_insufficient_personal_evidence"]
        if rejected:
            lines.extend([
                "## 附：打回候选（本人对题证据不足）",
                "",
                "| 主题 | 本人对题来源对话 | 来源文件命中 | 分类（本人/模板/跑题） |",
                "|---|---|---|---|",
            ])
            for d in rejected:
                c = d.get("classified", {})
                lines.append(
                    f"| `{d['theme']}` | {d.get('personal_docs', 0)} | "
                    f"{d.get('source_file_hits', 0)} | "
                    f"{c.get('personal_on_topic', 0)}/"
                    f"{c.get('prompt_or_external', 0)}/{c.get('off_topic', 0)} |"
                )
            lines.append("")
        lines.extend(["## 附：未进入候选的理由计数", ""])
        counts: dict[str, int] = {}
        for d in dropped:
            counts[d["reason"]] = counts.get(d["reason"], 0) + 1
        for reason, count in sorted(counts.items()):
            lines.append(f"- `{reason}`: {count}")
        lines.append("")
    return "\n".join(lines)


def run(profiles_dir: pathlib.Path, first_pass_md: pathlib.Path,
        db_path: pathlib.Path, out_dir: pathlib.Path, min_docs: int = 2) -> dict:
    profiles = l2.load_profiles(profiles_dir)
    fp = l2.parse_first_pass(first_pass_md)
    records = l2.load_records(db_path)
    candidates, dropped = mine_themes(records, profiles, fp, min_docs=min_docs)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "l2_candidates.md").write_text(
        render_theme_report(candidates, dropped), encoding="utf-8")
    patches_dir = out_dir / "l2_profile_patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    for name, body in l2.render_patches(candidates).items():
        (patches_dir / f"{name}.patch.md").write_text(body, encoding="utf-8")

    ledger = out_dir / "l2_review.jsonl"
    existing = l2.load_review_ledger(ledger)
    for c in candidates:
        existing.setdefault(c.candidate_id, {
            "candidate_id": c.candidate_id, "rec_id": c.rec_id, "layer": 2,
            "signal": c.signal, "target_profile": c.target_profile,
            "status": "pending", "needs_llm": True,
            "needs_llm_resolved": False, "reviewer": "", "note": "",
        })
    ledger.write_text(
        "\n".join(json.dumps(v, ensure_ascii=False) for v in existing.values()) + "\n",
        encoding="utf-8",
    )
    return {
        "records": len(records),
        "personal_records": sum(1 for r in records if r["role"] == "user"),
        "candidates": len(candidates),
        "dropped": len(dropped),
        "report": str(out_dir / "l2_candidates.md"),
        "patches_dir": str(patches_dir),
        "ledger": str(ledger),
        "themes": [c.candidate_id + ":" + c.signal for c in candidates],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="L2 cross-conversation theme miner.")
    ap.add_argument("--profiles", required=True, type=pathlib.Path)
    ap.add_argument("--first-pass", required=True, type=pathlib.Path)
    ap.add_argument("--db", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--min-docs", type=int, default=2)
    args = ap.parse_args()
    try:
        res = run(args.profiles, args.first_pass, args.db, args.out, args.min_docs)
    except (FileNotFoundError, ValueError) as exc:
        print(f"L2_THEME_ERROR: {exc}")
        return 2
    print("L2_THEME_OK " + " ".join(f"{k}={v}" for k, v in res.items() if k != "themes"))
    print("themes=" + json.dumps(res["themes"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
