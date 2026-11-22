#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 4: Validate a 6-file AI onboarding kit for completeness, clichés, placeholders, and PII/local-path leaks."""

from __future__ import annotations

import argparse
import calendar
import datetime
import pathlib
import re
import unicodedata

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

# Issue #2 / review E4: only a *quoted example adjacent to a rule verb* is exempt.
# A line merely containing 禁止 somewhere used to exempt every cliché on it.
_QUOTE_PAIRS = [
    ("'", "'"), ('"', '"'), ("`", "`"), ("“", "”"),
    ("‘", "’"), ("「", "」"), ("『", "』"), ("《", "》"), ("〈", "〉"),
]
_RULE_VERBS = ("禁止", "严禁", "不要说", "禁用水话", "别说", "禁止说", "禁止用", "严禁说", "不使用")
_RULE_CONNECTORS = ("", "说", "用", "：", ":", " ")

_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")
_CJK_DATE_RE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")


def _is_quoted_rule_example(line: str, cliche: str) -> bool:
    """Return True only for 禁止说“...” style intentional citations.

    A rule may list several quoted phrases in a row ("禁止说“A”“B”…"), so the
    rule verb must appear before the cliché and the span between them must not
    cross a sentence terminator. This still rejects
    “A”这是禁止的腔调, where the rule verb appears after the citation.
    """
    for open_q, close_q in _QUOTE_PAIRS:
        quoted = f"{open_q}{cliche}{close_q}"
        if quoted not in line:
            continue
        cliche_at = line.find(quoted)
        for verb in _RULE_VERBS:
            for conn in _RULE_CONNECTORS:
                marker = f"{verb}{conn}{open_q}"
                rule_at = line.find(marker)
                if rule_at == -1 or rule_at >= cliche_at:
                    continue
                if not re.search(r"[。！？；\n]", line[rule_at:cliche_at]):
                    return True
    return False


def _invalid_calendar_dates(text: str) -> list[str]:
    """Return impossible dates such as 2025-02-30; ignore month-only/version-like strings."""
    bad: list[str] = []
    for regex in (_DATE_RE, _CJK_DATE_RE):
        for m in regex.finditer(text):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (2000 <= y <= 2100 and 1 <= mo <= 12):
                bad.append(m.group(0))
                continue
            if not (1 <= d <= calendar.monthrange(y, mo)[1]):
                bad.append(m.group(0))
    return bad

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


# `[待确认]` tri-state scanning (CONFLICT-05 / issue #15):
# - A compliant marker: `[待确认] <疑点> ｜ 原文：「…」 ｜ 出处：<file>:<line>` -> INFO, never fails.
# - B bare marker: no source/quote -> PENDING_UNTRACEABLE in strict mode.
# - C meta-rule reference inside inline backticks or a fenced code block -> not counted.
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FENCE_RE = re.compile(r"^\s*```")
PENDING_TOKEN = "[待确认]"
HAS_QUOTE_RE = re.compile(r"原文\s*[:：]\s*\S")
HAS_SOURCE_RE = re.compile(r"出处\s*[:：]\s*\S")


def _scan_pending_markers(text: str) -> tuple[int, list[int], set[int]]:
    """Return (compliant_count, bare_line_numbers, pending_line_numbers).

    Lines inside fenced code blocks and inline backtick spans are ignored (case C),
    matching the previous `` `[待确认]` `` meta-rule exemption. The pending line
    numbers let the caller exempt marker shape lines from the placeholder check.
    """
    compliant = 0
    bare_lines: list[int] = []
    pending_lines: set[int] = set()
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scan_line = INLINE_CODE_RE.sub("", line)
        if PENDING_TOKEN not in scan_line:
            continue
        pending_lines.add(lineno)
        if HAS_QUOTE_RE.search(scan_line) and HAS_SOURCE_RE.search(scan_line):
            compliant += 1
        else:
            bare_lines.append(lineno)
    return compliant, bare_lines, pending_lines


# Issue #2 Bug C: natural-language uncertainty prose. The literal `[待确认]`
# marker only catches one surface form; a kit that writes the same doubt in
# prose ("记不清当时到底有没有发出去") used to pass both strict and
# non-strict. This channel reports NON-FATAL warnings: during the collection
# phase uncertainty is expected; the delivery phase can upgrade them to
# failures with `--fail-on-uncertain-prose`.
UNCERTAIN_PROSE_TERMS = [
    "记不清",
    "记不得",
    "记不住",
    "待核实",
    "未核实",
    "说不准",
    "不确定",
    "可能记错",
    "大概",
    "印象里",
    "好像",
    "忘了细节",
    "有待确认",
]

# Heuristic negation / already-confirmed contexts: a term sitting right after
# one of these is a closed statement, not an open doubt ("不是不确定",
# "已核实，不存在不确定"). Deliberately narrow; README documents what the
# heuristic does not cover, and `--uncertain-prose-ignore` gives line-level
# overrides for residual false positives.
_UNCERTAIN_NEGATION_PREFIXES = (
    "不是", "并非", "并不", "不算", "没有", "不存在",
    "已核实", "已确认", "排除", "无",
)

# Compounds where the hedge is only a substring of a technical term:
# "不确定度" (degree of uncertainty) is not a doubt hedge.
_COMPOUND_TAIL_EXCLUDE = {"不确定": ("度",)}


def _normalize_for_prose(text: str) -> str:
    """Fold full-width forms to half-width (NFKC) and strip all whitespace.

    Lets spaced or full-width variants such as "待 核 实" / "待　核　实" match
    the normalized term list; matching runs against the normalized text while
    the original line is still reported verbatim.
    """
    folded = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", folded)


def _is_negated_uncertainty(normalized: str, idx: int) -> bool:
    """True if the hit sits inside a narrow negation/confirmation window."""
    window = normalized[max(0, idx - 4):idx]
    return any(prefix in window for prefix in _UNCERTAIN_NEGATION_PREFIXES)


def scan_uncertain_prose(
    text: str, whitelist: list[str] | None = None
) -> list[dict[str, object]]:
    """Return hits: {"lineno", "term", "line"} for natural-language doubt.

    Fenced code blocks and inline backtick spans are skipped, matching the
    pending-marker scan. A line containing any whitelist substring is exempt.
    One hit per line keeps the report readable.
    """
    whitelist = whitelist or []
    hits: list[dict[str, object]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scan_line = INLINE_CODE_RE.sub("", line)
        if any(entry and entry in scan_line for entry in whitelist):
            continue
        normalized = _normalize_for_prose(scan_line)
        for term in UNCERTAIN_PROSE_TERMS:
            idx = normalized.find(_normalize_for_prose(term))
            if idx == -1:
                continue
            if _is_negated_uncertainty(normalized, idx):
                continue
            tail = normalized[idx + len(term): idx + len(term) + 1]
            if tail in _COMPOUND_TAIL_EXCLUDE.get(term, ()):
                continue
            hits.append({"lineno": lineno, "term": term, "line": line.strip()})
            break
    return hits


def validate_kit(
    target_dir: pathlib.Path,
    strict: bool = False,
    forbidden_terms: list[str] | None = None,
    fail_on_uncertain_prose: bool = False,
    uncertain_prose_whitelist: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Return (passed, diagnostics) checking all 6 kit files under target_dir."""
    diagnostics: list[str] = []
    if not target_dir.is_dir():
        return False, [f"Target directory missing: {target_dir}"]

    passed = True
    compliant_total = 0
    uncertain_total = 0

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
            for cliche in AI_CLICHES:
                if cliche in line and not _is_quoted_rule_example(line, cliche):
                    diagnostics.append(f"CLICHE found in {fname}: '{cliche}'")
                    passed = False

        invalid_dates = _invalid_calendar_dates(text)
        if invalid_dates:
            diagnostics.append(f"INVALID_DATE found in {fname}: {invalid_dates[:3]}")
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

        # `[待确认]` tri-state (CONFLICT-05): A compliant -> INFO; B bare -> fail;
        # C backtick/fence meta reference -> ignored by _scan_pending_markers.
        compliant, bare_lines, pending_lines = _scan_pending_markers(text)
        compliant_total += compliant
        for lineno in bare_lines:
            diagnostics.append(f"PENDING_UNTRACEABLE: {fname}:{lineno}")
            if strict:
                passed = False

        # Issue #2 Bug C: natural-language uncertainty (UNCERTAIN_PROSE).
        # Non-fatal warning even under --strict; the delivery phase upgrades
        # these to failures via fail_on_uncertain_prose.
        prose_hits = scan_uncertain_prose(text, uncertain_prose_whitelist)
        uncertain_total += len(prose_hits)
        for hit in prose_hits:
            diagnostics.append(
                f"UNCERTAIN_PROSE: {fname}:{hit['lineno']} "
                f"命中“{hit['term']}”｜原文：{hit['line']}"
            )
            if fail_on_uncertain_prose:
                passed = False

        # Pending marker shape lines are exempt from the placeholder check: the
        # documented shape uses `<疑点>` / `<file>:<line>`, which PLACEHOLDER_RE
        # would otherwise flag as unfilled on an otherwise compliant marker.
        placeholders: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno in pending_lines:
                continue
            placeholders.extend(PLACEHOLDER_RE.findall(line))
        if strict and placeholders:
            diagnostics.append(f"UNFILLED placeholders in {fname}: {placeholders[:5]}")
            passed = False

    if compliant_total > 0:
        diagnostics.append(
            f"INFO: {compliant_total} compliant '[待确认]' marker(s) pending backfill confirmation."
        )

    if uncertain_total > 0:
        diagnostics.append(
            f"WARN: {uncertain_total} line(s) carry natural-language uncertainty; "
            f"tag the fact with [待确认] or verify against source before delivery."
        )

    return passed, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the 6-file AI onboarding kit.")
    parser.add_argument("--target", required=True, type=pathlib.Path, help="Directory holding the 6 kit files")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on template placeholders or bare/untraceable [待确认]; compliant markers stay INFO",
    )
    parser.add_argument("--forbidden", nargs="*", default=[], help="Extra personal terms that must not appear")
    parser.add_argument(
        "--fail-on-uncertain-prose",
        action="store_true",
        help="Delivery phase: fail on UNCERTAIN_PROSE warnings; by default they stay non-fatal even under --strict",
    )
    parser.add_argument(
        "--uncertain-prose-ignore",
        nargs="*",
        default=[],
        help="Substrings that exempt a line from UNCERTAIN_PROSE (false-positive overrides)",
    )
    args = parser.parse_args()

    ok, msgs = validate_kit(
        args.target,
        strict=args.strict,
        forbidden_terms=args.forbidden,
        fail_on_uncertain_prose=args.fail_on_uncertain_prose,
        uncertain_prose_whitelist=args.uncertain_prose_ignore,
    )
    for m in msgs:
        print(m)
    print("VALIDATE_OK" if ok else "VALIDATE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
