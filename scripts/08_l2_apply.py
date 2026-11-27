#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Apply layer-2 candidates as an explicit, unsigned pending zone.

This is the mechanical half of the second backflow for a zero-config Agent:

    kit + l2_profile_patches -> kit_next (pending zone, never signed)

Safety boundary:
- it never writes into the official kit in place; output defaults to work/kit_next;
- every applied candidate keeps `[待确认]` plus 原文/出处;
- it never fills the 本人签字 blank, and never promotes a candidate to a fact;
- a candidate whose excerpt cannot be traced is skipped, not guessed;
- a target profile must carry an explicit end anchor
  `[XH-L2-PENDING-END]`; if the anchor is missing or duplicated the
  script fails without writing (no blind append to the file tail);
- an existing pending zone is never duplicated: all candidates already present
  means idempotent skip, otherwise the script stops and asks for a merge;
- `AGENTS.md` is read-only for this unsigned path, matching 05 `apply_signed`.

Why a separate evidence file?  The layer-2 candidates may come from records that
were not part of the bootstrap evidence digest.  We copy only the candidate
excerpts into `_evidence/l2-lines.md`, so the strict validator can resolve every
new citation without exposing the whole raw chat export.
"""

from __future__ import annotations

import argparse
import importlib
import os
import pathlib
import re
import shutil
import sys

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

VALIDATOR = importlib.import_module("03_validate_kit")

EVIDENCE_REL = pathlib.Path("_evidence") / "l2-lines.md"
PENDING_HEADER = "## 附：二层回流待确认区（机器候选，未签字）"
PENDING_HEADER_RE = re.compile(r"^## 附：二层回流待确认区(?:（机器候选，未签字）)?\s*$", re.M)
PENDING_ANCHOR = "[XH-L2-PENDING-END]"
QUESTION_RE = re.compile(
    r"(是不是|能不能|可不可以|有没有|在哪里|什么形式|怎么回事|为何|能否|"
    r"还是说|你可以看一下|请问|哪些|什么区别|什么意思|[？?])"
)
BLOCK_RE = re.compile(
    r"###\s*(?P<cid>L2-\d{4})\s*\[待确认\].*?"
    r"\*\*原文摘录\*\*：>\s*(?P<excerpt>[^\n]+)",
    re.S,
)


class L2ApplyError(RuntimeError):
    """A safe-stop condition: never write a partial or blind patch."""


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


def _atomic_write(path: pathlib.Path, text: str, *, backup: bool = True) -> None:
    """Write through a same-directory temp file, with a one-time .bak snapshot."""
    if backup and path.is_file():
        bak = path.with_name(path.name + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
    _atomic_write(path, "\n".join(lines) + "\n", backup=False)


def _check_existing_zone(text: str, cids: list[str], name: str) -> bool:
    """Return True when all candidates already exist; raise on a partial zone."""
    m = PENDING_HEADER_RE.search(text)
    if not m:
        if "L2-BACKFILL-BEGIN" in text:
            raise L2ApplyError(
                f"PENDING_ZONE_UNRECOGNIZED: {name} has a legacy L2 marker without a "
                "recognized heading; merge it by hand before re-running 08"
            )
        return False
    existing = set(re.findall(r"L2-\d{4}", text[m.start():]))
    if all(cid in existing for cid in cids):
        return True
    raise L2ApplyError(
        f"PENDING_ZONE_EXISTS: {name} already has an unsigned pending zone; "
        "refusing to append a second zone. Merge the new candidates by hand "
        "or remove the old zone first."
    )


def _validate_anchor(text: str, name: str) -> None:
    count = text.count(PENDING_ANCHOR)
    if count == 0:
        raise L2ApplyError(
            f"ANCHOR_MISSING: {name} has no {PENDING_ANCHOR}; refusing to append "
            "blindly to the file tail. Add the anchor at the end of the profile first."
        )
    if count > 1:
        raise L2ApplyError(
            f"ANCHOR_DUPLICATED: {name} contains {count} {PENDING_ANCHOR}; "
            "keep exactly one at the end"
        )
    after = text.split(PENDING_ANCHOR, 1)[1]
    if after.strip():
        raise L2ApplyError(
            f"ANCHOR_NOT_AT_END: {name} has content after {PENDING_ANCHOR}; "
            "move the anchor to the very end"
        )


def _insert_before_anchor(text: str, zone: list[str], name: str) -> str:
    _validate_anchor(text, name)
    before, _after = text.split(PENDING_ANCHOR, 1)
    prefix = before.rstrip()
    return prefix + "\n\n" + "\n".join(zone) + "\n" + PENDING_ANCHOR + "\n"


def apply_unsigned(
    kit: pathlib.Path,
    l2_dir: pathlib.Path,
    out_kit: pathlib.Path,
    *,
    enforce_score: bool = False,
) -> dict:
    if not kit.is_dir():
        raise L2ApplyError(f"KIT_DIR_MISSING: {kit}")
    if out_kit.resolve() == kit.resolve():
        raise L2ApplyError("OUT_KIT_MUST_DIFFER: refusing to modify the signed kit in place")
    if out_kit.exists():
        shutil.rmtree(out_kit)
    shutil.copytree(kit, out_kit)

    profile_blocks = parse_patches(l2_dir)
    # Assign line numbers before writing the evidence digest.
    numbered: dict[str, list[tuple[str, str, int]]] = {}
    targets: dict[str, pathlib.Path] = {}
    all_applied: list[tuple[str, str, int]] = []
    question_skipped = 0
    lineno = 5  # four header lines, first record at line 5
    for target, blocks in profile_blocks.items():
        real = VALIDATOR.find_kit_file(out_kit, target)
        if real is None:
            raise L2ApplyError(f"TARGET_MISSING: no kit file matches {target!r}")
        if real.name == "AGENTS.md":
            raise L2ApplyError(
                "AGENTS_READ_ONLY: the unsigned L2 path never edits AGENTS.md"
            )
        targets[target] = real
        numbered[target] = []
        for cid, excerpt in blocks:
            if QUESTION_RE.search(excerpt):
                question_skipped += 1
                continue
            numbered[target].append((cid, excerpt, lineno))
            all_applied.append((cid, excerpt, lineno))
            lineno += 1

    # Validate every target before any write: a missing anchor or a conflicting
    # unsigned zone must stop the run without touching the output copy.
    skip_targets: set[str] = set()
    for target, blocks in numbered.items():
        real = targets[target]
        text = real.read_text(encoding="utf-8", errors="replace")
        if _check_existing_zone(text, [cid for cid, _excerpt, _line in blocks], real.name):
            skip_targets.add(target)
        else:
            _validate_anchor(text, real.name)

    _write_evidence(out_kit, all_applied)

    applied = 0
    skipped_existing = 0
    for target, blocks in numbered.items():
        real = targets[target]
        if target in skip_targets:
            skipped_existing += len(blocks)
            continue
        text = real.read_text(encoding="utf-8", errors="replace")
        zone = [
            PENDING_HEADER,
            "",
            "> 机器生成，未经本人签字，不当作事实。",
            "",
        ]
        for cid, excerpt, line in blocks:
            zone.append(
                f"- [待确认] {cid} 二层回流候选 ｜ 原文：「{excerpt}」 ｜ "
                f"出处：{EVIDENCE_REL.as_posix()}:{line}"
            )
        zone.append("")
        _atomic_write(real, _insert_before_anchor(text, zone, real.name), backup=True)
        applied += len(blocks)

    ok, messages = VALIDATOR.validate_kit(out_kit, strict=True)
    card = VALIDATOR.score_kit(out_kit)
    score_ok = bool(card.get("overall_passed"))
    if enforce_score and not score_ok:
        ok = False
        messages = list(messages) + [
            "SCORECARD_ENFORCED: overall scorecard failed; candidate kit is not production-ready"
        ]
    return {
        "applied": applied,
        "skipped_existing": skipped_existing,
        "kit": str(out_kit),
        "validate_ok": ok,
        "validate_messages": messages,
        "question_skipped": question_skipped,
        "score_ok": score_ok,
        "scorecard": card,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply L2 candidates as an unsigned pending zone.")
    ap.add_argument("--kit", required=True, type=pathlib.Path)
    ap.add_argument("--l2", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--enforce-score", action="store_true",
                    help="fail when the scorecard is not met (default: report only)")
    args = ap.parse_args()
    try:
        res = apply_unsigned(args.kit, args.l2, args.out, enforce_score=args.enforce_score)
    except (L2ApplyError, FileNotFoundError, ValueError) as exc:
        print(f"L2_APPLY_ERROR: {exc}")
        return 2
    for msg in res["validate_messages"]:
        print(msg)
    print(
        f"L2_APPLY applied={res['applied']} skipped_existing={res['skipped_existing']} "
        f"question_skipped={res.get('question_skipped', 0)} kit={res['kit']} "
        f"validate={'OK' if res['validate_ok'] else 'FAILED'} "
        f"scorecard={'PASS' if res['score_ok'] else 'FAIL'}"
    )
    return 0 if res["validate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
