#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #98 / E6-T3: S7 three-question blind-test package and scoring rubric.

A blind tester (a fresh, isolated Agent) reads **only** the six kit files in the
package. Raw chat exports, the interview directory, the SQLite DB and L2
candidates are deliberately never copied, so the test cannot leak context.

Two artifacts are written to the package dir:

- `盲测三问.md`: the question sheet handed to the blind tester;
- `.expected.json`: scorer-only reference extracted from the kit (mainline /
  principle / rule facts), not shown to the blind tester.

PASS requires all three questions to be answerable from the kit; each question
returns its own PASS/FAIL and the evidence line the answer should cite.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import unicodedata

VALIDATOR = __import__("03_validate_kit")

KIT_FILE_ALIASES = {
    "AGENTS.md": ["AGENTS.md"],
    "00-总入口索引.md": ["00-总入口索引.md"],
    "01-身份与当前主线.md": ["01-身份与当前主线.md"],
    "02-核心判断准则.md": ["02-核心判断准则.md"],
    "03-硬规则与表达黑话.md": ["03-硬规则与表达黑话.md"],
    "04-正反例避坑账.md": ["04-正反例避坑账.md", "04-反面案例清单.md"],
}

SECTION_RULES = {
    "mainline": ("01-身份与当前主线.md", "当前主线候选"),
    "principle": ("02-核心判断准则.md", "有据判断"),
    "rule": ("03-硬规则与表达黑话.md", "硬规则"),
}

QUESTIONS = [
    ("Q1", "mainline", "当前主线是什么？只复述档案里的当前主线，不要补档案外的项目。"),
    ("Q2", "principle", "核心判断准则有哪些？能写代号就写代号（如 1A），再写要点。"),
    ("Q3", "rule", "硬规则 / 红线有哪些？逐条列出档案里的持久约束。"),
]

CODE_RE = re.compile(r"\d[A-Z]")
_BULLET_PREFIXES = ("- **候选", "- **A级·访谈")


def _normalize(text: str) -> str:
    compact = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[\s，。；、：:（）()「」『』/／·\-_]", "", compact)


def _bigrams(text: str) -> set[str]:
    norm = _normalize(text)
    return {norm[i:i + 2] for i in range(len(norm) - 1) if len(norm[i:i + 2]) == 2}


def _bullets(kit: pathlib.Path, file_name: str, heading: str) -> list[str]:
    fpath = VALIDATOR.find_kit_file(kit, file_name)
    if fpath is None:
        return []
    lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
    in_section = False
    out: list[str] = []
    for line in lines:
        if line.startswith("## "):
            in_section = heading in line
            continue
        if in_section and line.startswith(_BULLET_PREFIXES):
            out.append(line)
    return out


def _heading_text(bullet: str) -> str:
    # Strip the bullet marker, keep the heading before the first ｜ source block.
    body = re.sub(r"^- \*\*[^*]+\*\*\s*", "", bullet)
    return body.split("｜")[0].strip()


def extract_expected(kit: pathlib.Path) -> dict[str, object]:
    """Sorter-only reference: facts the blind tester should be able to cite."""
    expected: dict[str, object] = {}
    for slot, (file_name, heading) in SECTION_RULES.items():
        bullets = _bullets(kit, file_name, heading)
        headings = [_heading_text(b) for b in bullets]
        codes = sorted({m.group(0) for b in bullets for m in CODE_RE.finditer(b)}) if slot == "principle" else []
        expected[slot] = {"bullets": headings, "codes": codes, "count": len(bullets)}
    return expected


def build_blind_package(kit: pathlib.Path, out_dir: pathlib.Path) -> dict[str, object]:
    """Copy only the six kit files; write the question sheet and scorer reference."""
    out_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for canonical, aliases in KIT_FILE_ALIASES.items():
        for alias in aliases:
            src = kit / alias
            if src.is_file():
                shutil.copyfile(src, out_dir / canonical)
                copied.append(canonical)
                break

    expected = extract_expected(kit)
    (out_dir / ".expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")

    q_lines = [
        "# S7 三问盲测（独立 Agent 隔离会话）",
        "",
        "> 你只能读本包内的六份档案；**禁止**查阅原始聊天记录、访谈答案、数据库或其他上下文。",
        "> 答不出就写“档案里没有”，不要用常识补全；每条回答后面写档案出处（文件名 + 行/条目）。",
        "",
    ]
    for qid, slot, question in QUESTIONS:
        q_lines += [
            f"## {qid} {question}",
            "",
            "- 回答：",
            "- 出处：",
            "",
        ]
    q_lines += [
        "## 判定口径（评分用，不属于作答）",
        "",
        "- Q1：能答出唯一主线；Q2：能答出准则代号或要点；Q3：能答出至少一条硬规则。",
        "- 三问全部可从档案答出 → PASS；任一问档案内无据可答 → FAIL，并写明缺哪一问。",
        "",
    ]
    (out_dir / "盲测三问.md").write_text("\n".join(q_lines) + "\n", encoding="utf-8")

    return {"copied": copied, "expected": expected, "out": str(out_dir)}


def _answer_block(sheet: str, qid: str) -> str:
    m = re.search(rf"##\s*{qid}\b[^\n]*\n(.*?)(?:\n##\s+|\Z)", sheet, re.S)
    if not m:
        return ""
    ans = re.search(r"回答\s*[:：]\s*(.+)", m.group(1))
    return ans.group(1).strip() if ans else ""


def _answer_matches(answer: str, expected_bullets: list[str], codes: list[str]) -> bool:
    if not answer or answer in ("档案里没有", "无", "不知道"):
        return False
    norm = _normalize(answer)
    if codes and any(code in answer for code in codes):
        return True
    for bullet in expected_bullets:
        grams = _bigrams(bullet)
        if grams and len(grams & _bigrams(answer)) >= 2:
            return True
    return False


def score_answers(expected: dict[str, object], sheet: str) -> dict[str, object]:
    """Score a filled answer sheet against the scorer-only expected reference."""
    results: dict[str, object] = {}
    overall = True
    for qid, slot, _question in QUESTIONS:
        exp = expected[slot]  # type: ignore[index]
        answer = _answer_block(sheet, qid)
        matched = _answer_matches(answer, exp["bullets"], exp["codes"])  # type: ignore[index]
        # If the kit itself has no sourced fact for this slot, the question is
        # not answerable by design; report it as a gap rather than a tester miss.
        kit_empty = exp["count"] == 0  # type: ignore[index]
        passed = matched if not kit_empty else False
        overall = overall and passed
        results[qid] = {
            "slot": slot,
            "answer": answer,
            "kit_facts": exp["count"],
            "passed": passed,
            "reason": "matched" if matched else ("kit-empty" if kit_empty else "no-kit-evidence-match"),
        }
    return {"overall_passed": overall, "questions": results}


def main() -> int:
    ap = argparse.ArgumentParser(description="S7 blind three-question package and scorer")
    ap.add_argument("--kit", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--score", type=pathlib.Path, default=None,
                    help="filled answer sheet to score; without it, only build the package")
    args = ap.parse_args()

    if not args.kit.is_dir():
        print("BLIND_PACKAGE_FAIL: kit directory missing:", args.kit)
        return 2

    # P13: `--score` used to read the answer sheet AFTER build_blind_package(),
    # which overwrote `out/盲测三问.md` with a blank template. Read the answers
    # first, and restore them if the score file is the package's own sheet.
    sheet_text: str | None = None
    score_is_package_sheet = False
    if args.score:
        if not args.score.is_file():
            print("BLIND_SCORE_MISSING:", args.score)
            return 2
        sheet_text = args.score.read_text(encoding="utf-8", errors="replace")
        try:
            score_is_package_sheet = args.score.resolve() == (args.out / "盲测三问.md").resolve()
        except OSError:
            score_is_package_sheet = False

    package = build_blind_package(args.kit, args.out)
    print(f"BLIND_PACKAGE_OK copied={len(package['copied'])} out={args.out}")
    if sheet_text is not None and score_is_package_sheet:
        args.score.write_text(sheet_text, encoding="utf-8")
        print("BLIND_SCORE_SHEET_PRESERVED:", args.score)

    if args.score:
        expected = json.loads((args.out / ".expected.json").read_text(encoding="utf-8"))
        sheet = sheet_text if sheet_text is not None else args.score.read_text(encoding="utf-8")
        result = score_answers(expected, sheet)
        for qid, res in result["questions"].items():
            verdict = "PASS" if res["passed"] else "FAIL"
            print(f"[{verdict}] {qid} {res['slot']}: {res['reason']} (kit_facts={res['kit_facts']})")
        print("BLIND_PASS" if result["overall_passed"] else "BLIND_FAIL")
        return 0 if result["overall_passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
