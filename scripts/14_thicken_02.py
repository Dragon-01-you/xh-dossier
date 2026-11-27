#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thicken 02 with sourced judgements and collapse the mainline to one (#150 / T7).

Why this exists
---------------
02-核心判断准则 was an empty shell on the real kit: three machine padding
sentences ("先确认目标与验收，再谈执行速度" …) instead of any judgement the
user actually said, so the scorecard could never fill the ``principle`` slot
(coverage stuck at 5/6, "三问可答" at 2/3). 01 also kept three competing
"当前主线候选", so ``mainline_unique`` was 0.00.

What it does — and what it refuses to do
----------------------------------------
* Every 02 bullet quotes **one verbatim sentence** from
  ``_evidence/chat-lines.md`` and cites the physical line it came from. The
  selector is a rule set (tradeoff / priority markers, no questions, nothing
  addressed at the assistant), not a paraphrase: it either finds the user's own
  sentence or reports that there are too few.
* Demoted mainline candidates keep their sentence, ``原文`` and ``出处`` byte
  for byte; only their section changes, so "收敛只移动、不改写".
* ``03`` / ``04`` are hashed before and after and the run aborts if either byte
  moved.
* Idempotent: a second run prints ``NOOP`` and writes nothing.

Usage::

    python -X utf8 scripts/14_thicken_02.py --kit work/kit --dry-run
    python -X utf8 scripts/14_thicken_02.py --kit work/kit

Exit codes: 0 done / already done, 2 bad input or 03/04 changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import unicodedata

COUNTER_VERSION = "v1"
STEP = "14_thicken_02"

KIT_02 = "02-核心判断准则.md"
KIT_01 = "01-身份与当前主线.md"
FROZEN = ("03-硬规则与表达黑话.md", "04-反例避坑账.md", "04-反面案例清单.md")
EVIDENCE_REL = "_evidence/chat-lines.md"

EVIDENCE_ROW_RE = re.compile(
    r"^L\d{4} \| (?P<rec>REC-\d+) \| (?P<date>[\d-]+) \| user \| (?P<text>.*)$"
)
QUOTE_RE = re.compile(r"原文\s*[:：]\s*(?:「(?P<q1>.*?)」|“(?P<q2>.*?)”)")
BULLET_RE = re.compile(r"^-\s+\*\*(?P<label>[^*]+)\*\*\s*(?P<rest>.*)$")

# A durable judgement shows up as an explicit tradeoff or priority, not as a
# request. These are the only markers the selector trusts.
TRADEOFF_PATTERNS = (
    r"而不是",
    r"不是[^。！？；]{1,24}而是",
    r"宁可",
    r"优先",
    r"先[^。！？；]{1,14}再",
    r"不如",
    r"没必要",
    r"不值得",
    r"应该先",
    r"最重要",
    r"核心是",
    r"关键是",
    r"本质",
)
TRADEOFF_RE = re.compile("|".join(f"(?:{p})" for p in TRADEOFF_PATTERNS))

# A sentence aimed at the assistant in this turn is a request, not a standing
# view. Reuse the audit's own predicates so generator and validator agree.
ADDRESSED_RE = re.compile(
    r"(我说叫你|我说了|我要你|不然我要你|你安排完|你最后|你帮我|你可以看一下|你看一下|"
    r"你去|你给我|你直接|你先把|你先给|你按照|你能不能|你深度|你帮我看看|你就是要|"
    r"你不能|你不要|你别|你切记|切记哈|你这里|你那个|你这|你搞|你在干|你把|你在|你能)"
)
# A sentence that starts as an errand is a request, not a standing judgement.
REQUEST_RE = re.compile(
    r"(请帮我|请你|帮我|麻烦你|帮我看看|麻烦|你可以|你看|你先|你给我|按照|先把|先给|"
    r"去看看|去看|去找|搜一下|搜索一下|深入|研究一下|给我|告诉我)"
)
LIST_ITEM_RE = re.compile(r"^\d+[.、)）]\s*")
# Markdown / table residue is export noise, not a sentence the user spoke.
NOISE_RE = re.compile(r"\*\*|\|")
NEGATIVE_CUES = (
    "踩坑", "失败", "返工", "报错", "崩", "重来", "不行", "卡住", "白做",
    "浪费时间", "没完成", "什么都没", "没听懂", "没达到", "有问题", "搞错",
    "没做", "没发",
)
# Sentence openers that mark a conclusion drawn from experience.
CONCLUSION_OPENERS = ("其实", "所以", "本质上", "总的来说", "说到底", "毕竟")

MIN_LEN = 12
MAX_LEN = 70
MAX_PER_RECORD = 2
MIN_PRINCIPLES = 3
DEFAULT_LIMIT = 5
PADDING_SENTENCES = (
    "先确认目标与验收，再谈执行速度",
    "先保真实与可复现，再谈漂亮表达",
    "先做最小闭环，再扩规模",
)


class ThickenError(Exception):
    """Input or invariant violated; message names the failing step."""


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_sentences(text: str) -> list[str]:
    """Split a chat message into sentences without rewriting a single character."""
    norm = unicodedata.normalize("NFKC", text)
    return [p.strip() for p in re.split(r"(?<=[。！？!?；;])", norm) if p.strip()]


def evidence_rows(evidence_text: str) -> list[dict[str, object]]:
    """Parse the read-only evidence digest into citable rows (physical line numbers)."""
    rows: list[dict[str, object]] = []
    for lineno, line in enumerate(evidence_text.splitlines(), start=1):
        hit = EVIDENCE_ROW_RE.match(line)
        if not hit:
            continue
        rows.append({
            "line": lineno,
            "rec": hit.group("rec"),
            "date": hit.group("date"),
            "text": hit.group("text"),
        })
    return rows


def quoted_sentences(kit_files: list[str]) -> set[str]:
    """Every 原文 already cited anywhere in the kit, normalized for de-duplication."""
    seen: set[str] = set()
    for text in kit_files:
        for line in text.splitlines():
            hit = QUOTE_RE.search(line)
            if not hit:
                continue
            quote = hit.group("q1") or hit.group("q2") or ""
            seen.add(_norm(quote))
    return seen


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def judge_sentences(text: str) -> list[tuple[int, str]]:
    """Return every verbatim tradeoff/priority sentence in one chat message.

    The contract is the same as ``04_bootstrap_kit.candidate_sentence``: never
    paraphrase. A message either contains usable sentences or contributes
    nothing. Several distinct judgements may live in one message, so all of
    them are returned ranked; the caller caps how many survive.
    """
    found: list[tuple[int, str]] = []
    for sent in split_sentences(text):
        sent = re.sub(r"^[#>*\-\s]+", "", sent).strip()
        if not (MIN_LEN <= len(sent) <= MAX_LEN):
            continue
        if sent.endswith(("？", "?")):
            continue
        if LIST_ITEM_RE.match(sent):
            continue
        if ADDRESSED_RE.search(sent):
            continue
        if REQUEST_RE.search(sent):
            continue
        if NOISE_RE.search(sent):
            continue
        if any(cue in sent for cue in NEGATIVE_CUES):
            continue
        if not TRADEOFF_RE.search(sent):
            continue
        score = 1 + len(TRADEOFF_RE.findall(sent))
        if sent.startswith(CONCLUSION_OPENERS):
            score += 1
        found.append((score, sent))
    found.sort(key=lambda item: (-item[0], -len(item[1])))
    return found


def pick_principles(
    rows: list[dict[str, object]],
    already_cited: set[str],
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, object]]:
    """Rank sourced judgement sentences: strongest first, at most two per record."""
    scored: list[tuple[int, int, dict[str, object]]] = []
    for row in rows:
        for score, sentence in judge_sentences(str(row["text"])):
            if _norm(sentence) in already_cited:
                continue
            scored.append((score, len(sentence), {**row, "sentence": sentence}))
    scored.sort(key=lambda item: (-item[0], -item[1], str(item[2]["rec"])))

    picked: list[dict[str, object]] = []
    per_record: dict[str, int] = {}
    seen: set[str] = set()
    for _score, _length, row in scored:
        if len(picked) >= limit:
            break
        rec = str(row["rec"])
        if per_record.get(rec, 0) >= MAX_PER_RECORD:
            continue
        key = _norm(str(row["sentence"]))
        if key in seen:
            continue
        seen.add(key)
        per_record[rec] = per_record.get(rec, 0) + 1
        picked.append(row)
    return picked


def existing_principle_bullets(text: str) -> list[str]:
    """Sourced bullets already sitting under 02's 有据判断 section."""
    in_section = False
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = "有据判断" in line
            continue
        if in_section and line.startswith(("- **候选", "- **A级·访谈")):
            if QUOTE_RE.search(line) and "出处" in line:
                out.append(line)
    return out


def reliebel(line: str, idx: int) -> str:
    """Keep a bullet's body byte for byte and only re-sequence its 候选 label."""
    return re.sub(r"^- \*\*[^*]+\*\*", f"- **候选-{idx:02d}**", line, count=1)


def render_02(existing: list[str], picked: list[dict[str, object]]) -> str:
    """Render the canonical 02. No padding sentences, ever.

    Existing sourced bullets are carried over verbatim (only the label is
    re-sequenced); new ones are appended. A second run therefore cannot silently
    replace what the first run found.
    """
    lines = [
        "# 02-核心判断准则",
        "",
        "> **机器初稿 / B 级**：判断句必须来自用户原话并带出处；机器归纳标题不能冒充本人原话。",
        "> 访谈选定的准则列为 **A 级**；raw 回填只作补证，与 A 级不一致时标 `[待确认]`。",
        "",
        "## 一、有据判断（原话 + 出处）",
        "",
    ]
    idx = 0
    for line in existing:
        idx += 1
        lines.append(reliebel(line, idx))
    for row in picked:
        idx += 1
        sentence = str(row["sentence"])
        lines.append(
            f"- **候选-{idx:02d}** {sentence} ｜ 原文：「{sentence}」 ｜ "
            f"出处：{EVIDENCE_REL}:{row['line']} ｜ 来源通道：raw 回填 B 级"
        )
    total = idx
    if total == 0:
        lines.append(
            "- 需访谈：数据库中没有足够的「判断/取舍」原话；请补访谈或更多聊天，"
            "不用推测或归纳填空。"
        )
    elif total < MIN_PRINCIPLES:
        lines += [
            "",
            f"- 原话不足 {MIN_PRINCIPLES} 条（只找到 {total} 条）；其余判断需访谈补全，不用归纳句填空。",
        ]
    lines += [
        "",
        "## 二、待补访谈",
        "",
        "- 本文件不写机器归纳出来的取舍顺序；归纳内容只能在本人确认原话后升格。",
        "- 上面每条仍然只是候选：本人逐条标「是/不是」之后，才升格为 A 级准则。",
        "",
    ]
    return "\n".join(lines)


def collapse_mainline(text: str) -> tuple[str, list[str], list[str]]:
    """Keep one current mainline; move the rest verbatim into a history section.

    Returns ``(new_text, kept_labels, moved_lines)``. The moved bullets are the
    original lines, unchanged, so the user's sentence, ``原文`` and ``出处``
    survive the move.
    """
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines)
         if line.startswith("## ") and "当前主线候选" in line),
        None,
    )
    if start is None:
        raise ThickenError(f"{KIT_01} 缺少「当前主线候选」章节")

    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    bullets = [i for i in range(start + 1, end) if lines[i].startswith("- **候选")]
    if not bullets:
        return text, [], []

    kept_idx = bullets[0]
    moved_idx = bullets[1:]
    moved_lines = [lines[i] for i in moved_idx]

    body = [line for i, line in enumerate(lines) if i not in set(moved_idx)]
    # `body` is shorter now; recompute the history anchor by heading text.
    if not moved_lines:
        return "\n".join(body) + ("\n" if text.endswith("\n") else ""), [lines[kept_idx]], []

    history_heading = "## 六、历史主线候选（不是当前主线）"
    block = ["", history_heading, ""]
    block += [
        "- 以下原句与出处逐字保留；只换了章节。当前主线只留 §二 的第 1 条，"
        "其余降级为历史候选，等本人重新确认。",
        "",
    ]
    block += moved_lines
    block.append("")

    if history_heading in body:
        at = body.index(history_heading)
        tail = body[at:]
        head = body[:at]
        merged = head + block + tail[1:]
    else:
        # Append-only: existing sections keep their numbering and bytes.
        while body and body[-1] == "":
            body.pop()
        merged = body + block

    while merged and merged[-1] == "":
        merged.pop()
    out = "\n".join(merged)
    if text.endswith("\n"):
        out += "\n"
    return out, [lines[kept_idx]], moved_lines


def count_mainline(text: str) -> int:
    """Number of `- **候选` bullets inside the 当前主线候选 section."""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines)
         if line.startswith("## ") and "当前主线候选" in line),
        None,
    )
    if start is None:
        return 0
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return sum(1 for i in range(start + 1, end) if lines[i].startswith("- **候选"))


def count_sourced_principle(text: str) -> int:
    """Number of sourced bullets under 02's 有据判断 section."""
    return len(existing_principle_bullets(text))


def run(kit: pathlib.Path, limit: int, dry_run: bool) -> dict[str, object]:
    if not kit.is_dir():
        raise ThickenError(f"kit 目录不存在：{kit}")
    path_02 = kit / KIT_02
    path_01 = kit / KIT_01
    evidence_path = kit / EVIDENCE_REL
    for path in (path_02, path_01, evidence_path):
        if not path.is_file():
            raise ThickenError(f"缺少输入文件：{path}")

    frozen_before = {name: sha256(kit / name) for name in FROZEN if (kit / name).is_file()}

    text_01, text_02 = read(path_01), read(path_02)
    rows = evidence_rows(read(evidence_path))
    already = quoted_sentences([text_01, text_02] + [
        read(kit / name) for name in ("00-总入口索引.md", "AGENTS.md")
        if (kit / name).is_file()
    ])

    principle_before = count_sourced_principle(text_02)
    mainline_before = count_mainline(text_01)
    existing = existing_principle_bullets(text_02)

    already_done = principle_before >= limit or (
        principle_before >= MIN_PRINCIPLES and mainline_before <= 1
    )
    if already_done:
        return {
            "result": "NOOP",
            "principle_before": principle_before,
            "principle_after": principle_before,
            "mainline_before": mainline_before,
            "mainline_after": mainline_before,
        }

    room = max(0, limit - principle_before)
    picked = pick_principles(rows, already, limit=room) if room else []
    new_02 = render_02(existing, picked)
    new_01, kept, moved = collapse_mainline(text_01)

    principle_after = count_sourced_principle(new_02)
    mainline_after = count_mainline(new_01)

    if not dry_run:
        write(path_02, new_02)
        if new_01 != text_01:
            write(path_01, new_01)
        frozen_changed = [
            name for name, digest in frozen_before.items()
            if (kit / name).is_file() and sha256(kit / name) != digest
        ]
        if frozen_changed:
            raise ThickenError(f"03/04 必须零改动，但被改动了：{', '.join(frozen_changed)}")

    return {
        "result": "DRY_RUN" if dry_run else "DONE",
        "evidence_rows": len(rows),
        "principle_before": principle_before,
        "principle_after": principle_after,
        "mainline_before": mainline_before,
        "mainline_after": mainline_after,
        "kept_mainline": len(kept),
        "moved_mainline": len(moved),
        "frozen": sorted(frozen_before),
        "picked": [
            {"line": row["line"], "rec": row["rec"], "sentence": row["sentence"]}
            for row in picked
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="用带出处的原话加厚 02，并把 01 主线收敛成 1 条。")
    ap.add_argument("--kit", required=True, type=pathlib.Path, help="6 份档案所在目录")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"最多摘录几条判断句（默认 {DEFAULT_LIMIT}）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--json", action="store_true", help="输出一行 JSON 台账")
    args = ap.parse_args(argv)

    try:
        summary = run(args.kit, args.limit, args.dry_run)
    except ThickenError as exc:
        print(f"THICKEN_FAIL {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if summary["result"] == "NOOP":
        print("THICKEN_NOOP 02 已有带出处的判断、主线已唯一，未改动任何文件")
        return 0
    print(
        f"THICKEN_{summary['result']} principle {summary['principle_before']} → "
        f"{summary['principle_after']}；mainline {summary['mainline_before']} → "
        f"{summary['mainline_after']}（移出 {summary['moved_mainline']} 条）"
    )
    for item in summary["picked"]:
        print(f"  + L{item['line']:04d} {item['rec']} {item['sentence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
