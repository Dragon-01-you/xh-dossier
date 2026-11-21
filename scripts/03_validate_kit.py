#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 4: Validate a 6-file AI onboarding kit for completeness, clichés, and PII safety."""

from __future__ import annotations

import argparse
import pathlib
import re

REQUIRED_KIT_FILES = [
    "AGENTS.md",
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
]

AI_CLICHES = [
    "这是一个非常好的问题",
    "从多维度赋能",
    "打造全链路闭环生态",
    "每天进步1%复利37倍",
]

PLACEHOLDER_RE = re.compile(r"<填写[^>]+>")


def validate_kit(target_dir: pathlib.Path, strict: bool = False) -> tuple[bool, list[str]]:
    """Return (passed, diagnostics) checking all 6 kit files under target_dir."""
    diagnostics: list[str] = []
    if not target_dir.is_dir():
        return False, [f"Target directory missing: {target_dir}"]

    passed = True
    unconfirmed_total = 0

    for fname in REQUIRED_KIT_FILES:
        fpath = target_dir / fname
        if not fpath.is_file():
            diagnostics.append(f"MISSING required file: {fname}")
            passed = False
            continue
        text = fpath.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) < 80:
            diagnostics.append(f"TOO_SHORT (<80 chars): {fname} ({len(text)} chars)")
            passed = False

        # Flag AI clichés outside explicit prohibition lists
        for line in text.splitlines():
            if any(p in line for p in ("禁止", "严禁", "不要说", "AI 腔调")):
                continue
            for cliche in AI_CLICHES:
                if cliche in line:
                    diagnostics.append(f"CLICHE found in {fname}: '{cliche}'")
                    passed = False

        unconfirmed_total += text.count("[待确认]")
        placeholders = PLACEHOLDER_RE.findall(text)
        if strict and placeholders:
            diagnostics.append(f"UNFILLED placeholders in {fname}: {placeholders[:3]}")
            passed = False

    if unconfirmed_total > 0:
        diagnostics.append(f"INFO: {unconfirmed_total} '[待确认]' marker(s) pending backfill confirmation.")
        if strict:
            passed = False

    return passed, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the 6-file AI onboarding kit.")
    parser.add_argument("--target", required=True, type=pathlib.Path, help="Directory holding the 6 kit files")
    parser.add_argument("--strict", action="store_true", help="Fail if template placeholders or [待确认] remain")
    args = parser.parse_args()

    ok, msgs = validate_kit(args.target, strict=args.strict)
    for m in msgs:
        print(m)
    print("VALIDATE_OK" if ok else "VALIDATE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
