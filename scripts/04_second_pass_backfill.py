#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.3 / Second-pass backfill: mine UNTOLD information from the cold DB.

EXPERIMENTAL — DO NOT treat output as verified facts. See Issue #6 and the
task book at outputs/二次回流机制任务书.md. Known limits (honest, measured):

  1. This prototype has NO write-back into the 6 hot-load files and NO sign-off
     loop. It only produces candidates. The user's "second backfill" (a real
     second pass over the already-backfilled files) is NOT implemented here.
  2. Repeated-phrase extraction uses character n-grams and on real 729-record
     data produced auxiliary words (可以看一下 / 我觉得你可以) as top "themes".
     Those are noise, not signal.
  3. Complaint/mistake detection counts markers over a whole record, so long
     prompt/tutorial records (podcast scripts, skill docs) get false positives.
  4. Semantic-mismatch detection is a coarse heuristic (pattern ownership),
     not embedding-based; some mismatches (e.g. REC-0010) are missed.

Unlike 02_four_way_match.py (which queries with preset keywords/patterns = only
checks what you already said), this script attempts the REVERSE: surface content
NOT captured by preset patterns. It is a starting point, not the finished layer-2
mechanism. Reviewers: please attack items 1-4 above.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sqlite3
from collections import defaultdict
from typing import Iterable

COMPLAINT_MARKERS = ("太累", "实在", "每次都要", "总是", "又", "还是没", "居然", "错了", "没发出去", "拖了", "错过", "喊停", "反复", "重新解释")
RECURRING_MISTAKE = ("没理解", "记错", "跑偏", "没上线", "停在最后", "一直没发", "改细节", "忘", "临时", "重来")
NEGATION = ("先不要", "不要", "先别", "别直接", "禁止", "绝不")


def load_records(db_path: pathlib.Path) -> list[dict[str, str]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(
            "SELECT rec_id, source_file, created_at, role, content FROM records ORDER BY rec_id"
        ).fetchall()]
    finally:
        con.close()


def load_pattern_claims(backfill_md: pathlib.Path | None) -> dict[str, list[str]]:
    """Map REC id -> pattern titles that claimed it in the first pass.

    Key: a REC merely APPEARING in the report is NOT semantic coverage. We parse
    which pattern section each REC sits under, so we can detect semantic mismatch
    (one REC claimed by an unrelated pattern just because of a keyword overlap).
    """
    if not backfill_md or not backfill_md.is_file():
        return {}
    text = backfill_md.read_text(encoding="utf-8", errors="replace")
    claims: dict[str, list[str]] = defaultdict(list)
    current_pattern = "(keyword-only hit)"
    for line in text.splitlines():
        m = re.match(r"### 模式：`(.+?)`", line)
        if m:
            current_pattern = m.group(1)
            continue
        for rec in re.findall(r"REC-\d{4}", line):
            if current_pattern not in claims[rec]:
                claims[rec].append(current_pattern)
    return dict(claims)


def complaint_score(content: str) -> int:
    return sum(1 for m in COMPLAINT_MARKERS if m in content)


def mistake_score(content: str) -> int:
    return sum(1 for m in RECURRING_MISTAKE if m in content)


def has_negation(content: str) -> bool:
    return any(n in content for n in NEGATION)


def find_repeated_phrases(records: list[dict[str, str]], min_len: int = 4) -> list[tuple[str, int]]:
    """Find repeated 4-8 char phrases across records (signal of an untold recurring theme)."""
    counts: dict[str, set[str]] = defaultdict(set)
    for r in records:
        text = re.sub(r"\s+", "", r["content"])
        for n in (5, 6, 7, 8):
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                if re.search(r"[\u4e00-\u9fff]", gram):
                    counts[gram].add(r["rec_id"])
    repeated = [(g, len(ids)) for g, ids in counts.items() if len(ids) >= 2 and len(g) >= min_len]
    # keep the longest representative phrases to avoid substring explosion
    repeated.sort(key=lambda x: (x[1], len(x[0])), reverse=True)
    kept: list[tuple[str, int]] = []
    for g, n in repeated:
        if any(g in prev for prev, _ in kept):
            continue
        kept.append((g, n))
        if len(kept) >= 20:
            break
    return kept


def run_second_pass(
    db_path: pathlib.Path,
    backfill_md: pathlib.Path | None,
) -> dict:
    records = load_records(db_path)
    claims = load_pattern_claims(backfill_md)
    user_records = [r for r in records if r["role"] == "user"]

    recurring = []
    for r in user_records:
        cs, ms = complaint_score(r["content"]), mistake_score(r["content"])
        if cs >= 2 or ms >= 1:
            tag = "complaint" if cs >= 2 else "recurring_mistake"
            claimed_by = claims.get(r["rec_id"], [])
            # Semantic mismatch: strong signal but claimed by no real pattern,
            # or only by the "(keyword-only hit)" bucket.
            semantic_mismatch = not any(c != "(keyword-only hit)" for c in claimed_by)
            recurring.append({
                "rec_id": r["rec_id"],
                "created_at": r["created_at"],
                "content": r["content"],
                "complaint_score": cs,
                "mistake_score": ms,
                "tag": tag,
                "negation": has_negation(r["content"]),
                "claimed_by": claimed_by,
                "semantic_mismatch": semantic_mismatch,
            })

    # Layer-2 gold: high-signal records whose meaning no preset pattern captured.
    untold = [x for x in recurring if x["semantic_mismatch"]]
    repeated_phrases = find_repeated_phrases(user_records)

    return {
        "total_records": len(records),
        "user_records": len(user_records),
        "first_pass_claimed": len(claims),
        "repeat_complaints_or_mistakes": recurring,
        "untold_candidates": untold,
        "repeated_phrases": repeated_phrases,
    }


def render_report(report: dict) -> str:
    lines = [
        "# 二层回流候选（untold-backfill）",
        "",
        f"> 原文 `{report['total_records']}` 条（用户 `{report['user_records']}` 条）｜一层有模式归属的 `{report['first_pass_claimed']}` 条。",
        "> 本表**不预设模式**，反向挖掘：重复抱怨、反复错误，以及一层只靠关键词命中、语义其实没覆盖的高信号记录。",
        "",
        "## 一、跨记录重复出现的短语（未说出口的主题）",
        "",
    ]
    for phrase, n in report["repeated_phrases"]:
        lines.append(f"- 「{phrase}」出现于 `{n}` 条记录")
    lines.extend(["", "## 二、重复抱怨 / 反复错误（带否定词标注，需人工辨别）", ""])
    for item in report["repeat_complaints_or_mistakes"]:
        flag = "⚠否定句" if item["negation"] else ""
        claimed = "、".join(item["claimed_by"]) if item["claimed_by"] else "无"
        mismatch = "**← 语义错配：一层没真正覆盖**" if item["semantic_mismatch"] else ""
        lines.append(
            f"- `[{item['rec_id']} | {item['created_at']}]` [{item['tag']} 抱怨{item['complaint_score']}/错误{item['mistake_score']}] {flag} · 一层归属：{claimed} {mismatch}\n"
            f"  - {item['content']}"
        )
    lines.extend(["", "## 三、二层深度回流建议（5 份热加载档案）", ""])
    for item in report["untold_candidates"]:
        lines.append(f"- `[{item['rec_id']}]` → 高信号且一层语义未覆盖，建议二次深度回流：**{item['content'][:70]}…**")
    if not report["untold_candidates"]:
        lines.append("- （本次样本中，重复抱怨均已被一层覆盖；真实数据下此处应出现新条目。）")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Second-pass backfill: mine untold info, not preset-pattern matches.")
    ap.add_argument("--db", required=True, type=pathlib.Path)
    ap.add_argument("--backfill", type=pathlib.Path, default=None, help="First-pass backfill_candidates.md to diff against")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()
    report = run_second_pass(args.db, args.backfill)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_report(report), encoding="utf-8")
    print(
        f"SECOND_PASS_OK records={report['total_records']} "
        f"repeat_signals={len(report['repeat_complaints_or_mistakes'])} "
        f"untold={len(report['untold_candidates'])} "
        f"phrases={len(report['repeated_phrases'])} out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
