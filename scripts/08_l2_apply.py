#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Apply layer-2 candidates as an explicit, unsigned pending zone.

This is the mechanical half of the second backflow for a zero-config Agent:

    kit + l2_profile_patches -> kit_next (pending zone, never signed)

Safety boundary:
- it never writes into the official kit in place; output defaults to work/kit_next;
- every applied candidate keeps `[待确认]` plus 原文/出处;
- it never fills the 本人签字 blank, and never promotes a candidate to a fact;
- a candidate whose excerpt cannot be traced is skipped, not guessed.

Why a separate evidence file?  The layer-2 candidates may come from records that
were not part of the bootstrap evidence digest.  We copy only the candidate
excerpts into `_evidence/l2-lines.md`, so the strict validator can resolve every
new citation without exposing the whole raw chat export.
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import re
import shutil
import sys

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

VALIDATOR = importlib.import_module("03_validate_kit")
BACKFILL = importlib.import_module("05_deep_backfill")

EVIDENCE_REL = pathlib.Path("_evidence") / "l2-lines.md"
# Issue #94 + #131: pure AI-directed questions stay out of the pending zone,
# while multi-sentence personal reflections with an incidental rhetorical `?` pass.
QUESTION_RE = BACKFILL.QUESTION_RE
BLOCK_RE = re.compile(
    r"###\s*(?P<cid>L2-\d{4})\s*\[待确认\].*?"
    r"\*\*原文摘录\*\*：>\s*(?P<excerpt>[^\n]+)",
    re.S,
)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("｜", " | ").replace("「", "『").replace("」", "』")
    return text[:220]


def parse_patches(l2_dir: pathlib.Path) -> dict[str, list[tuple[str, str]]]:
    patches = l2_dir / "l2_profile_patches"
    out: dict[str, list[tuple[str, str]]] = {}
    if not patches.is_dir():
        return out
    for patch in sorted(patches.glob("*.patch.md")):
        target = patch.name[: -len(".patch.md")]
        blocks = [(m.group("cid"), _clean(m.group("excerpt")))
                  for m in BLOCK_RE.finditer(patch.read_text(encoding="utf-8", errors="replace"))]
        if blocks:
            out[target] = blocks
    return out


def _write_evidence(out_kit: pathlib.Path, applied: list[tuple[str, str, int]]) -> None:
    path = out_kit / EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 二层回流候选证据行（只读）",
        "",
        "> 只收录已写入待确认区的候选原文；编号用于二层回流区的「出处」列。",
        "",
    ]
    for cid, excerpt, _line in applied:
        lines.append(f"{cid} | {excerpt}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_unsigned(kit: pathlib.Path, l2_dir: pathlib.Path, out_kit: pathlib.Path) -> dict:
    if not kit.is_dir():
        raise FileNotFoundError(f"KIT_DIR_MISSING: {kit}")
    if out_kit.resolve() == kit.resolve():
        raise ValueError("OUT_KIT_MUST_DIFFER: refusing to modify the signed kit in place")
    if out_kit.exists():
        shutil.rmtree(out_kit)
    shutil.copytree(kit, out_kit)

    profile_blocks = parse_patches(l2_dir)
    # Assign line numbers before writing the evidence digest.
    numbered: dict[str, list[tuple[str, str, int]]] = {}
    all_applied: list[tuple[str, str, int]] = []
    question_skipped = 0
    lineno = 5  # four header lines, first record at line 5
    for target, blocks in profile_blocks.items():
        real = VALIDATOR.find_kit_file(out_kit, target)
        if real is None:
            continue
        numbered[target] = []
        for cid, excerpt in blocks:
            if BACKFILL.is_pure_question_message(excerpt):
                question_skipped += 1
                continue
            numbered[target].append((cid, excerpt, lineno))
            all_applied.append((cid, excerpt, lineno))
            lineno += 1

    _write_evidence(out_kit, all_applied)

    applied = 0
    for target, blocks in numbered.items():
        real = VALIDATOR.find_kit_file(out_kit, target)
        if real is None:
            continue
        text = real.read_text(encoding="utf-8", errors="replace")
        if "二层回流待确认区（机器候选，未签字）" in text:
            continue
        zone = [
            "",
            "## 附：二层回流待确认区（机器候选，未签字）",
            "",
            "> 机器生成，未经本人签字，不当作事实。",
            "",
        ]
        for cid, excerpt, line in blocks:
            zone.append(
                f"- [待确认] {cid} 二层回流候选 ｜ 原文：「{excerpt}」 ｜ "
                f"出处：{EVIDENCE_REL.as_posix()}:{line}"
            )
        zone += [""]
        real.write_text(text.rstrip() + "\n" + "\n".join(zone), encoding="utf-8")
        applied += len(blocks)

    ok, messages = VALIDATOR.validate_kit(out_kit, strict=True)
    return {"applied": applied, "kit": str(out_kit), "validate_ok": ok,
            "validate_messages": messages, "question_skipped": question_skipped}


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply L2 candidates as an unsigned pending zone.")
    ap.add_argument("--kit", required=True, type=pathlib.Path)
    ap.add_argument("--l2", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()
    try:
        res = apply_unsigned(args.kit, args.l2, args.out)
    except (FileNotFoundError, ValueError) as exc:
        print(f"L2_APPLY_ERROR: {exc}")
        return 2
    for msg in res["validate_messages"]:
        print(msg)
    print(f"L2_APPLY applied={res['applied']} question_skipped={res.get('question_skipped', 0)} "
          f"kit={res['kit']} validate={'OK' if res['validate_ok'] else 'FAILED'}")
    return 0 if res["validate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
