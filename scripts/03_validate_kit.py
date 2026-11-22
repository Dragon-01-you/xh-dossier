#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 4: Validate a 6-file AI onboarding kit for completeness, clichés, placeholders, and PII/local-path leaks."""

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

# Match unfilled template instruction placeholders, both Chinese (<填写...>) and
# ASCII (<YYYY-MM>, <your_name>, <TODO>). Exclude real autolinks such as
# <https://example.com> and <mailto:...>.
PLACEHOLDER_RE = re.compile(r"<(?!(?:https?://|mailto:))[^>\n]{2,100}>")
# Detect accidentally leaked local user paths or secrets outside sanitized sample examples.
# Each pattern is anchored on a format that is unambiguous in prose, to keep false
# positives near zero on real Chinese kit files (dates, versions, counts must not fire).
SENSITIVE_PATH_RE = re.compile(
    r"(?:"
    # Local user home paths: only the homedir segment is sensitive, not any absolute path.
    r"[A-Za-z]:\\Users\\[^\\\s]+"
    r"|/Users/[^/\s]+"
    r"|/home/[^/\s]+"
    # OpenAI-style keys
    r"|sk-[A-Za-z0-9]{16,}"
    # GitHub tokens: ghp_/gho_/ghu_/ghs_/ghr_ + 36 chars, or fine-grained github_pat_
    r"|gh[pousr]_[A-Za-z0-9]{36,}"
    r"|github_pat_[A-Za-z0-9_]{22,}"
    # AWS access key id
    r"|AKIA[0-9A-Z]{16}"
    # PRC mobile number: 1[3-9] + 9 digits, bounded so long digit runs do not match.
    r"|(?<!\d)1[3-9]\d{9}(?!\d)"
    # PRC resident ID: 6-digit area + 8-digit birthdate + 3 digits + checksum (digit or X).
    # Anchor the birth date to a plausible 19xx/20xx range to avoid matching stray numbers.
    r"|(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
    r")"
)


def validate_kit(
    target_dir: pathlib.Path,
    strict: bool = False,
    forbidden_terms: list[str] | None = None,
) -> tuple[bool, list[str]]:
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

        for line in text.splitlines():
            if any(p in line for p in ("禁止", "严禁", "不要说", "AI 腔调")):
                continue
            for cliche in AI_CLICHES:
                if cliche in line:
                    diagnostics.append(f"CLICHE found in {fname}: '{cliche}'")
                    passed = False

        leaked_paths = SENSITIVE_PATH_RE.findall(text)
        if leaked_paths:
            diagnostics.append(f"PII_OR_SECRET_RISK found in {fname}: {leaked_paths[:2]}")
            passed = False

        if forbidden_terms:
            for term in forbidden_terms:
                if term and term in text:
                    diagnostics.append(f"FORBIDDEN_PII_TERM '{term}' found in {fname}")
                    passed = False

        # Skip backtick-quoted meta references like `[待确认]` in AI collaboration instructions (e.g. AGENTS.md)
        cleaned_for_unconfirmed = re.sub(r"`\[待确认\]`", "", text)
        unconfirmed_total += cleaned_for_unconfirmed.count("[待确认]")
        placeholders = PLACEHOLDER_RE.findall(text)
        if strict and placeholders:
            diagnostics.append(f"UNFILLED placeholders in {fname}: {placeholders[:5]}")
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
    parser.add_argument("--forbidden", nargs="*", default=[], help="Extra personal terms that must not appear")
    args = parser.parse_args()

    ok, msgs = validate_kit(args.target, strict=args.strict, forbidden_terms=args.forbidden)
    for m in msgs:
        print(m)
    print("VALIDATE_OK" if ok else "VALIDATE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
