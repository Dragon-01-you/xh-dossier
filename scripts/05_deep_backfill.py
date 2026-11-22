#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.4: Layer-2 DEEP backfill — a real second pass over already-backfilled profiles.

Issue #6. Design doc: docs/design-layer2-deep-backfill.md.

Layer 1 (02_four_way_match.py) verifies what you DID say (told content).
Layer 2 (this script) mines what you did NOT say: forgotten, unwritten,
or not-yet-realized information, then writes Candidates -> review ledger ->
human/AI sign-off -> (only then) patch back into the 6 hot-load profiles.

THREE inputs are mandatory — without A (profiles) and B (layer-1 report) this
is just the experimental 04 prototype, not a real second pass:
  A. --profiles        the 6 profile files (read-only) => "already told" index
  B. --first-pass      layer-1 backfill_candidates.md => pending + pattern claims
  C. --db              cold SQLite index (records table) => source material

Outputs (three):
  1. work/l2_candidates.md        main report, every item [待确认]
  2. work/l2_profile_patches/*.patch.md   per-profile controlled patch zone
  3. work/l2_review.jsonl         sign-off ledger (state machine)

NEVER modifies the official profile body unless --apply-signed --confirm is given
AND the ledger row is status=signed with a recorded reviewer + timestamp.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Literal

# ---------------------------------------------------------------- constants

PROFILE_FILES = (
    "AGENTS.md", "00-总入口索引.md", "01-身份与当前主线.md",
    "02-核心判断准则.md", "03-硬规则与表达黑话.md", "04-反面案例清单.md",
)

STOPWORDS = {
    "可以", "看一下", "一下", "我觉得", "这里", "的话", "那个", "这个", "其实",
    "就是", "可能", "应该", "一些", "进行", "相关", "对应", "一个", "然后",
    "反正", "好像", "有点", "我们", "什么", "怎么", "这些", "那些", "已经",
}
# Common content-word characters (verbs/nouns/adjectives) — filters out pure
# auxiliary phrases. Extensible; jieba.posseg could replace this if available.
CONTENT_HINT = set(
    "开工定验收标准做完交付上线拖延踩坑放弃闲鱼振兴杯笔记知识库向量回流截图封面钩子公司群"
    "工验收准备文件返复理解问题学习项目任务时间日月年份代码工具脚本数据报告内容方案"
    "改错失败成功试换删改建读看写说听做买卖教练习记录整理发布解释重新开始结束"
)

NON_PERSONAL_PREFIX = (
    "你是一名", "你是", "绝对铁律", "任务:", "任务：", "# 角色", "## 角色",
)
NON_PERSONAL_INNER = (
    "📑 智能总结", "Thought Process", "播客稿", "播客访谈", "感谢收听",
    "skill://", "plugin://", "[操作电脑]", "[Seed Audio", "[GitHub]",
    "内容类型", "内容总结", "时长", "https://", "http://",
)
NEGATION = ("先不要", "不要", "先别", "别直接", "禁止", "绝不", "别帮我")
SUBJECT_USER_MISS = ("我没听懂", "我没看懂", "没明白你说的")
SUBJECT_AI_MISS = ("你还是没理解", "你没理解", "没听懂你讲", "完全没理解我")
EXPERIENCE_MARKERS = ("我", "我们", "本人", "上次", "最近", "当时", "结果", "后来")
COMPLAINT_CUES = ("太累", "实在", "每次都要", "总是", "还是没", "居然", "错了", "没发出去", "拖了", "错过", "喊停", "反复", "重新解释")
MISTAKE_CUES = ("没理解", "记错", "跑偏", "没上线", "停在最后", "一直没发", "改细节", "忘了", "重来")

# Signal type -> (target profile, section anchor)
PROFILE_SECTION_MAP = {
    "recurring_mistake": ("04-反面案例清单.md", "## 二、反例标本"),
    "positive_pattern": ("04-反面案例清单.md", "## 一、正例标本"),
    "complaint": ("02-核心判断准则.md", "## 三、术"),
    "core_fact": ("01-身份与当前主线.md", "## 一、不可篡改的核心事实"),
    "hard_rule": ("03-硬规则与表达黑话.md", "## 一、对任何接手 AI 的 11 条硬规则"),
    "index_flow": ("00-总入口索引.md", "## 二、七步闭环流程"),
}
AGENTS_READ_ONLY = True

Status = Literal["pending", "reviewed", "signed", "archived", "rejected", "needs_llm"]
SENT_SPLIT_RE = re.compile(r"[。！？!?\n；;]")
REC_RE = re.compile(r"REC-\d{4}")
CLAUSE_DATE_RE = re.compile(r"20\d{2}[-/年]\d{1,2}")


@dataclass
class CoverageIndex:
    covered_rec_ids: set[str] = field(default_factory=set)
    terms_by_profile: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class FirstPassIndex:
    pending_rec_ids: set[str] = field(default_factory=set)
    claims: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class PhraseHit:
    phrase: str
    doc_count: int


@dataclass
class L2Candidate:
    candidate_id: str
    rec_id: str
    created_at: str
    signal: str
    target_profile: str
    section_anchor: str
    evidence: str
    excerpt: str
    source_file: str
    cross_ref: str = "none"
    needs_llm: bool = True
    status: Status = "pending"


# ---------------------------------------------------------------- inputs

def load_profiles(profile_dir: pathlib.Path) -> dict[str, str]:
    if not profile_dir.is_dir():
        raise FileNotFoundError(f"PROFILE_DIR_MISSING: {profile_dir}")
    out: dict[str, str] = {}
    for name in PROFILE_FILES:
        p = profile_dir / name
        if not p.is_file():
            # The 6th file has a known naming variant; accept both.
            alt = profile_dir / "04-正反例避坑账.md"
            if name.startswith("04-") and alt.is_file():
                p = alt
            else:
                raise FileNotFoundError(f"PROFILE_FILE_MISSING: {name}")
        out[name] = p.read_text(encoding="utf-8", errors="replace")
    return out


def build_coverage_index(profiles: dict[str, str]) -> CoverageIndex:
    idx = CoverageIndex()
    for name, text in profiles.items():
        idx.covered_rec_ids |= set(REC_RE.findall(text))
        # chunk into 4-12 char CJK n-grams as coarse topic terms
        cjk = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        terms: set[str] = set()
        for block in cjk:
            for n in (4, 6, 8):
                for i in range(len(block) - n + 1):
                    g = block[i:i + n]
                    if not any(sw in g for sw in STOPWORDS):
                        terms.add(g)
        idx.terms_by_profile[name] = terms
    return idx


def parse_first_pass(backfill_md: pathlib.Path) -> FirstPassIndex:
    if not backfill_md.is_file():
        raise FileNotFoundError(f"MISSING_FIRST_PASS_INPUT: {backfill_md}")
    text = backfill_md.read_text(encoding="utf-8", errors="replace")
    fp = FirstPassIndex()
    fp.pending_rec_ids = set(REC_RE.findall(text))
    claims: dict[str, list[str]] = {}
    current = "(keyword-only hit)"
    for line in text.splitlines():
        m = re.match(r"### 模式：`(.+?)`", line)
        if m:
            current = m.group(1)
            continue
        for rec in REC_RE.findall(line):
            claims.setdefault(rec, [])
            if current not in claims[rec]:
                claims[rec].append(current)
    fp.claims = claims
    return fp


def load_records(db_path: pathlib.Path) -> list[dict[str, str]]:
    if not db_path.is_file():
        raise FileNotFoundError(f"DB_MISSING: {db_path}")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(
            "SELECT rec_id, source_file, created_at, role, content FROM records ORDER BY rec_id"
        )]
    finally:
        con.close()


# ---------------------------------------------------------------- gates

def classify_narrative(content: str) -> tuple[bool, str]:
    """Return (is_personal_experience, reason). Design §4.2."""
    c = content.strip()
    if len(c) > 600:
        return False, "non_personal:too_long"
    if any(c.startswith(p) for p in NON_PERSONAL_PREFIX):
        return False, "non_personal:prompt_prefix"
    if any(tok in c for tok in NON_PERSONAL_INNER):
        return False, "non_personal:ai_or_material"
    if not any(m in c for m in EXPERIENCE_MARKERS):
        return False, "non_personal:no_first_person"
    if len(c) < 15:
        return False, "non_personal:too_short"
    return True, "personal"


def split_sentences(content: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT_RE.split(content) if s.strip()]


def sentence_signals(sentences: list[str]) -> dict[str, object]:
    """Design §4.3 + self-review fix: only count the USER'S OWN setbacks.

    Self-review found a large false-positive class on real data: sentences like
    "你这个不太行 / 我觉得你可以去看一下 / 我还是没太懂" are FEEDBACK/requests
    to the AI or help-seeking, NOT the user's own recurring mistake. They were
    being labeled 'complaint' and mis-routed into 02-核心判断准则.md.

    A complaint/mistake signal now requires BOTH:
      (a) first-person subject, AND
      (b) a self-setback cue describing something that happened to the USER
          (没发出去/拖了/错过/太累/每次都要重...), AND
      (c) NOT an evaluation/request aimed at the AI ("你这个/你可以/我觉得你").
    """
    complaint = 0
    mistake = 0
    ambiguous = 0
    filtered: list[str] = []
    # Narrow, unambiguous self-setback cues. Dropped "又没/又要" (too wide —
    # appeared in AI-directed instructions and caused false positives).
    self_setback_cues = ("没发出去", "没上线", "拖了四天", "错过截止", "实在太累",
                         "每次都要重新", "反复如此", "停在最后10%")
    # Medium cues: could be a self-setback OR an AI-directed complaint. Rules
    # cannot decide — surface these as needs_llm rather than dropping them.
    ambiguous_cues = ("太累", "错过", "拖了", "反复", "每次都要", "没发出去", "没上线")
    ai_directed = ("你这个", "你的", "你可以", "我觉得你", "你需要", "请你",
                   "帮我", "给我", "看一下这个", "没太懂", "不太懂", "没听懂你")
    for s in sentences:
        if not any(m in s for m in EXPERIENCE_MARKERS):
            continue
        has_user_miss = any(u in s for u in SUBJECT_USER_MISS)
        has_ai_miss = any(a in s for a in SUBJECT_AI_MISS)
        if has_user_miss and not has_ai_miss:
            filtered.append("subject_object_inversion")
            continue
        head = s[:12]
        if any(n in head for n in NEGATION):
            filtered.append("negation")
            continue
        # Exclude feedback/help-seeking aimed at the AI.
        if any(a in s for a in ai_directed) and not any(c in s for c in self_setback_cues):
            # Rule cannot tell a real self-setback from an AI-directed complaint
            # when medium cues appear — queue for human/LLM judgement.
            if any(c in s for c in ambiguous_cues):
                ambiguous += 1
            filtered.append("ai_directed_not_self_setback")
            continue
        if any(c in s for c in self_setback_cues):
            complaint += 1
        if any(m in s for m in MISTAKE_CUES) and any(c in s for c in self_setback_cues):
            mistake += 1
    return {"complaint": complaint, "mistake": mistake, "filtered": filtered,
            "ambiguous": ambiguous}


def mine_repeated_phrases(records: list[dict[str, str]], min_docs: int = 2,
                          min_len: int = 4, max_len: int = 12) -> list[PhraseHit]:
    """Design §4.1: content-word n-grams across DIFFERENT source files."""
    docs_by_phrase: dict[str, set[str]] = {}
    for r in records:
        for block in re.findall(r"[\u4e00-\u9fff]{2,}", r["content"]):  # punctuation boundary
            for n in (4, 6, 8, 12):
                for i in range(len(block) - n + 1):
                    g = block[i:i + n]
                    if not (min_len <= len(g) <= max_len):
                        continue
                    # STOPWORDS contains multi-char words, so test SUBSTRING
                    # containment, not per-character membership (which let
                    # "可以看一下" through because no single char is a stopword).
                    if any(sw in g for sw in STOPWORDS):
                        continue
                    if not any(ch in CONTENT_HINT for ch in g):
                        continue
                    docs_by_phrase.setdefault(g, set()).add(r["source_file"])
    hits = [PhraseHit(g, len(docs)) for g, docs in docs_by_phrase.items() if len(docs) >= min_docs]
    hits.sort(key=lambda h: (h.doc_count, len(h.phrase)), reverse=True)
    kept: list[PhraseHit] = []
    for h in hits:
        if any(h.phrase in k.phrase for k in kept):
            continue
        kept.append(h)
    return kept[:20]


# ---------------------------------------------------------------- pipeline

def _topic_overlap(content: str, terms: set[str]) -> int:
    blocks = re.findall(r"[\u4e00-\u9fff]{4,}", content)
    grams = {g for b in blocks for g in (b[i:i+8] for i in range(max(0, len(b)-7))) if len(g) == 8}
    return len(grams & terms)


def coverage_decide(records: list[dict[str, str]], coverage: CoverageIndex,
                    first_pass: FirstPassIndex) -> tuple[list[L2Candidate], list[dict[str, str]]]:
    """Design §4.4 C0~C3. Returns (candidates, dropped_with_reason)."""
    candidates: list[L2Candidate] = []
    dropped: list[dict[str, str]] = []
    phrases = mine_repeated_phrases(records)
    repeated_texts = {p.phrase for p in phrases}

    personal = [r for r in records if r["role"] == "user"]
    for r in personal:
        ok, reason = classify_narrative(r["content"])
        if not ok:
            dropped.append({"rec_id": r["rec_id"], "reason": reason})
            continue
        signals = sentence_signals(split_sentences(r["content"]))
        if not (signals["complaint"] or signals["mistake"]):
            # Self-review fix: rule cannot decide ambiguous self-setback vs
            # AI-directed feedback. Keep them visible as needs_llm, never as a
            # conclusion and never silently dropped.
            if signals.get("ambiguous", 0):
                dropped.append({"rec_id": r["rec_id"], "reason": "needs_llm_ambiguous",
                                "excerpt": r["content"][:120]})
            else:
                dropped.append({"rec_id": r["rec_id"], "reason": "no_self_setback_signal"})
            continue
        # C0 — already in profiles
        if r["rec_id"] in coverage.covered_rec_ids:
            dropped.append({"rec_id": r["rec_id"], "reason": "C0_covered_by_profile"})
            continue
        covered_any = any(_topic_overlap(r["content"], terms) >= 2
                          for terms in coverage.terms_by_profile.values())
        if covered_any:
            dropped.append({"rec_id": r["rec_id"], "reason": "C0_topic_covered"})
            continue
        cross_ref = "none"
        # C1 — already a layer-1 [待确认] item: cross-reference, do not duplicate
        if r["rec_id"] in first_pass.pending_rec_ids:
            cross_ref = "L1"
        # C2 — claimed by a REAL layer-1 pattern: do not re-produce
        real_claims = [c for c in first_pass.claims.get(r["rec_id"], [])
                       if c != "(keyword-only hit)"]
        if real_claims and cross_ref != "L1":
            dropped.append({"rec_id": r["rec_id"], "reason": "C2_claimed_by_L1_pattern"})
            continue

        if signals["mistake"] or "踩坑" in r["content"] or any(p in r["content"] for p in ("改细节", "没上线", "停在最后")):
            stype = "recurring_mistake"
        elif "放弃" in r["content"] or "彻底" in r["content"]:
            stype = "core_fact"
        elif "禁止" in r["content"] or "绝不" in r["content"]:
            stype = "hard_rule"
        elif "索引" in r["content"] or "回流" in r["content"] or "挂载" in r["content"]:
            stype = "index_flow"
        else:
            stype = "complaint"
        target, anchor = PROFILE_SECTION_MAP[stype]
        excerpt = re.sub(r"\s+", " ", r["content"])[:200]

        candidates.append(L2Candidate(
            candidate_id="",  # assigned after sort
            rec_id=r["rec_id"],
            created_at=r["created_at"],
            signal=stype,
            target_profile=target,
            section_anchor=anchor,
            evidence=(f"抱怨{int(signals['complaint'])}/错误{int(signals['mistake'])}; "
                      f"门禁过滤={','.join(str(x) for x in signals['filtered']) or '无'}; "
                      f"跨对话短语命中={sum(1 for p in repeated_texts if p in r['content'])}"),
            excerpt=excerpt,
            source_file=r["source_file"],
            cross_ref=cross_ref,
        ))
    candidates.sort(key=lambda c: (c.cross_ref != "L1", c.rec_id))
    for i, c in enumerate(candidates, 1):
        c.candidate_id = f"L2-{i:04d}"
    return candidates, dropped


# ---------------------------------------------------------------- outputs

WARNING_BANNER = (
    "> ⚠️ **二层回流候选 · 全部 [待确认] · 未经本人签字不得写入正式档案。**\n"
    "> 每条都需本人确认「是否亲历」+ 独立 AI 双尺审查；`needs_llm=true` 表示语义判断未做，不得跳过。\n"
)


def render_candidates(candidates: list[L2Candidate], dropped: list[dict[str, str]] | None = None) -> str:
    lines = ["# L2 二层深度回流候选报告", "", WARNING_BANNER,
             f"> 共 `{len(candidates)}` 条候选（其中 L1 交叉引用 "
             f"`{sum(1 for c in candidates if c.cross_ref == 'L1')}` 条）。", ""]
    needs_llm = [d for d in (dropped or []) if d["reason"] == "needs_llm_ambiguous"]
    if needs_llm:
        lines.extend(["## 附：需语义判断（needs_llm · 规则拿不准，未列入候选）", ""])
        for d in needs_llm[:15]:
            lines.append(f"- `[{d['rec_id']}]` {d.get('excerpt','')[:80]}…")
        lines.append("")
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
    return "\n".join(lines)


def render_patches(candidates: list[L2Candidate]) -> dict[str, str]:
    patches: dict[str, list[str]] = {}
    for c in candidates:
        block = [
            f"### {c.candidate_id} [待确认] [{c.rec_id} | {c.created_at}] 建议位置：{c.target_profile} / {c.section_anchor}",
            f"- **信号**：{c.signal} ｜ {c.evidence}",
            f"- **原文摘录**：> {c.excerpt}",
            "- **复核**：□ 本人亲历  □ AI 代做/转述/材料  □ 已讲过  □ 值得升格",
            "- **独立 AI 双尺审查**：□ 规范尺  □ 需求尺（≤3 轮）",
            "- **本人签字**：__________  日期：__________",
            "",
        ]
        patches.setdefault(c.target_profile, []).extend(block)
    out: dict[str, str] = {}
    for name, body in patches.items():
        out[name] = (
            "<!-- L2-BACKFILL-BEGIN · 机器生成 · 未经本人签字不生效 -->\n"
            "## 附：二层回流待确认区\n\n"
            + "\n".join(body)
            + "<!-- L2-BACKFILL-END -->\n"
        )
    return out


def load_review_ledger(path: pathlib.Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            rows[obj["candidate_id"]] = obj
        except (json.JSONDecodeError, KeyError):
            continue
    return rows


_SIGN_STATE: dict[str, set[Status]] = {
    "pending": {"reviewed", "rejected", "needs_llm"},
    "reviewed": {"signed", "rejected", "needs_llm"},
    "needs_llm": {"reviewed", "rejected"},
    "signed": {"archived"},
    "archived": set(),
    "rejected": set(),
}


def update_review(path: pathlib.Path, candidate_id: str, status: Status,
                  reviewer: str, note: str = "") -> dict:
    ledger = load_review_ledger(path)
    row = ledger.get(candidate_id, {"candidate_id": candidate_id, "layer": 2, "status": "pending"})
    old = row.get("status", "pending")
    if status not in _SIGN_STATE.get(old, set()):
        raise ValueError(f"ILLEGAL_STATE_TRANSITION: {old} -> {status} for {candidate_id}")
    if status == "signed" and not reviewer:
        raise ValueError("SIGNATURE_REQUIRES_REVIEWER: signed needs --by")
    row.update({
        "status": status,
        "reviewer": reviewer,
        "note": note,
        "reviewed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "signed_at": datetime.datetime.now().isoformat(timespec="seconds") if status == "signed" else row.get("signed_at"),
    })
    ledger[candidate_id] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(v, ensure_ascii=False) for v in ledger.values()) + "\n", encoding="utf-8")
    return row


def apply_signed(patches_dir: pathlib.Path, profiles_dir: pathlib.Path,
                 ledger: dict[str, dict], confirm: bool) -> dict:
    """Only signed candidates, only with explicit --confirm. AGENTS.md stays read-only."""
    if not confirm:
        return {"applied": 0, "reason": "NEEDS_CONFIRM"}
    applied = 0
    for cid, row in ledger.items():
        if row.get("status") != "signed":
            continue
        target = row.get("target_profile", "")
        if not target or (AGENTS_READ_ONLY and target == "AGENTS.md"):
            continue
        actual = profiles_dir / target
        if not actual.is_file():
            alt = profiles_dir / "04-正反例避坑账.md"
            if target.startswith("04-") and alt.is_file():
                actual = alt
        patch = patches_dir / f"{target}.patch.md"
        if not patch.is_file() or not actual.is_file():
            continue
        body = patch.read_text(encoding="utf-8", errors="replace")
        if cid not in body:
            continue
        text = actual.read_text(encoding="utf-8", errors="replace")
        if "L2-BACKFILL-END" in text:
            continue  # already has a pending zone; human merges manually
        actual.write_text(text.rstrip() + "\n\n" + body, encoding="utf-8")
        row["status"] = "archived"
        applied += 1
    return {"applied": applied, "reason": "ok"}


def run_deep_backfill(profiles_dir: pathlib.Path, first_pass_md: pathlib.Path,
                      db_path: pathlib.Path, out_dir: pathlib.Path) -> dict:
    profiles = load_profiles(profiles_dir)
    coverage = build_coverage_index(profiles)
    fp = parse_first_pass(first_pass_md)   # will raise if missing — mandatory input
    records = load_records(db_path)
    candidates, dropped = coverage_decide(records, coverage, fp)

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "l2_candidates.md"
    report_path.write_text(render_candidates(candidates, dropped), encoding="utf-8")

    patches_dir = out_dir / "l2_profile_patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    for name, body in render_patches(candidates).items():
        (patches_dir / f"{name}.patch.md").write_text(body, encoding="utf-8")

    ledger_path = out_dir / "l2_review.jsonl"
    if not ledger_path.exists():
        ledger_path.write_text("", encoding="utf-8")

    return {
        "records": len(records),
        "personal_records": sum(1 for r in records if r["role"] == "user"),
        "candidates": len(candidates),
        "dropped": len(dropped),
        "cross_ref_L1": sum(1 for c in candidates if c.cross_ref == "L1"),
        "report": str(report_path),
        "patches_dir": str(patches_dir),
        "ledger": str(ledger_path),
        "dropped_by_reason": _reason_counts(dropped),
    }


def _reason_counts(dropped: list[dict[str, str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in dropped:
        out[d["reason"]] = out.get(d["reason"], 0) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Layer-2 deep backfill (candidates -> review -> sign -> patch).")
    ap.add_argument("--profiles", type=pathlib.Path, help="Directory of the 6 hot-load profile files")
    ap.add_argument("--first-pass", type=pathlib.Path, help="Layer-1 backfill_candidates.md (MANDATORY)")
    ap.add_argument("--db", type=pathlib.Path, help="Cold index SQLite DB")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("work/l2_out"), help="Output dir")
    ap.add_argument("--sign", help="Candidate id to sign/review")
    ap.add_argument("--status", default="signed", help="New status for --sign")
    ap.add_argument("--by", default="", help="Reviewer name (required for signed)")
    ap.add_argument("--note", default="")
    ap.add_argument("--apply-signed", action="store_true", help="Write signed candidates into profiles")
    ap.add_argument("--confirm", action="store_true", help="Second confirmation for --apply-signed")
    args = ap.parse_args()

    ledger_path = args.out / "l2_review.jsonl"
    if args.sign:
        row = update_review(ledger_path, args.sign, args.status, args.by, args.note)  # type: ignore[arg-type]
        print(f"REVIEW_OK {row['candidate_id']} -> {row['status']}")
        return 0
    if args.apply_signed:
        res = apply_signed(args.out / "l2_profile_patches", args.profiles,
                           load_review_ledger(ledger_path), args.confirm)
        print(f"APPLY_SIGNED applied={res['applied']} reason={res['reason']}")
        return 0
    if not (args.profiles and args.first_pass and args.db):
        ap.error("--profiles, --first-pass and --db are all required for candidate generation")
    res = run_deep_backfill(args.profiles, args.first_pass, args.db, args.out)
    print("L2_BACKFILL_OK " + " ".join(f"{k}={v}" for k, v in res.items() if k != "dropped_by_reason"))
    print("dropped_by_reason=" + json.dumps(res["dropped_by_reason"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
