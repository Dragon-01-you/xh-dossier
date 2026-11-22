#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 4: Validate a 6-file AI onboarding kit for completeness, clichés, placeholders, and PII/local-path leaks."""

from __future__ import annotations

import argparse
import calendar
import pathlib
import re
import unicodedata

# Issue #2 / #15 scope (all merged on main):
#   - Bug A: cliché check no longer skips a whole line merely because it contains
#     禁止/严禁/...; only an intentional quoted example after a rule verb is exempt.
#   - Impossible calendar dates (INVALID_DATE) hard-fail in both modes.
#   - Bug B: an unsourced/bare `[待确认]` fails under --strict (PENDING_UNTRACEABLE);
#     a compliant marker stays INFO.
#   - Bug C: natural-language doubt without a literal marker (记不清/待核实/说不准...)
#     hard-fails in both modes as UNCERTAIN_SEMANTIC.
#   - #15: a cited source must resolve inside the kit dir or an explicitly approved
#     --source-root; absolute/drive-letter/`..` citations are traversal and fail.
REQUIRED_KIT_FILES = [
    "AGENTS.md",
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
]

# Real user kits often name the fourth file 04-反面案例清单.md. Accept that
# spelling without weakening the six-file contract or the output filenames.
KIT_FILE_ALIASES = {
    "04-正反例避坑账.md": ["04-反面案例清单.md", "04-正反例避坑账.md"],
}


def find_kit_file(target_dir: pathlib.Path, canonical: str) -> pathlib.Path | None:
    for name in KIT_FILE_ALIASES.get(canonical, [canonical]):
        candidate = target_dir / name
        if candidate.is_file():
            return candidate
    return None

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
_RULE_CONNECTORS = ("", "说", "用", "写", "提", "出现", "输出", "：", ":", " ")

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
# Runtime variables such as `<任务>` / `<项目>` / `<日期>` / `<分支>` are semantic
# slots, not unfilled template fields. Keep them visible to users, but do not fail
# strict validation for them.
RUNTIME_VAR_RE = re.compile(r"<(?:任务|项目|日期|分支)>")
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
    # Tencent Cloud / generic cloud keys (bootstrap already masks these; the
    # validator is the second line of defence against hand-written files).
    r"|AKID[A-Za-z0-9]{10,}"
    r"|(?:SecretId|SecretKey|AccessKeyId|AccessKeySecret)\s*[:：=]\s*[A-Za-z0-9/+=]{8,}"
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
#
# Bug B (issue #2): the strict failure on a bare marker conflicts with SKILL.md rule 4.
# That conflict is NOT relaxed here; the provenance-checking fix lands on the #15 branch
# (feat/t15-citation-check). Bug C: this scanner only matches the literal PENDING_TOKEN;
# natural-language uncertainty (记不清 / 待核实 / 说不准 / ...) is detected by the
# UNCERTAIN_PROSE channel in PR #47 (feat/t2c-uncertain-prose).
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FENCE_RE = re.compile(r"^\s*```")
PENDING_TOKEN = "[待确认]"
HAS_QUOTE_RE = re.compile(r"原文\s*[:：]\s*\S")
HAS_SOURCE_RE = re.compile(r"出处\s*[:：]\s*\S")
SOURCE_REF_RE = re.compile(r"出处\s*[:：]\s*(?P<src>[^｜|]+)")
QUOTE_TEXT_RE = re.compile(r"原文\s*[:：]\s*(?:「(?P<q1>.*?)」|“(?P<q2>.*?)”|\"(?P<q3>.*?)\"|'(?P<q4>.*?)')")
SOURCE_LINE_RE = re.compile(r"^(?P<path>.*?):(?P<line>\d+)(?:-\d+)?$")
_ABS_REF_RE = re.compile(r"^(?:[A-Za-z]:|[\\/])")
# Issue #2 Bug C: natural-language uncertainty is the same unresolved claim as a
# literal [待确认] marker. Keep the list narrow on purpose: broad words like
# "模糊/不确定" occur in legitimate rules ("把模糊想法变清晰").
UNCERTAIN_SEMANTIC_RE = re.compile(
    r"(记不清|记不得|记不住|记混|待核实|待人工核实|未核实|说不准|拿不准|没印象|想不起来|可能记错|可能记混|我不确定|我拿不准)"
)


def _scan_pending_markers(text: str) -> tuple[int, list[int], set[int], list[int]]:
    """Return (compliant_count, bare_line_numbers, pending_line_numbers, compliant_lines).

    Lines inside fenced code blocks and inline backtick spans are ignored (case C),
    matching the previous `` `[待确认]` `` meta-rule exemption. The pending line
    numbers let the caller exempt marker shape lines from the placeholder check.
    """
    compliant = 0
    bare_lines: list[int] = []
    pending_lines: set[int] = set()
    compliant_lines: list[int] = []
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
            compliant_lines.append(lineno)
        else:
            bare_lines.append(lineno)
    return compliant, bare_lines, pending_lines, compliant_lines


def _scan_uncertain_semantics(text: str) -> list[int]:
    """Return line numbers with natural-language uncertainty but no marker.

    A line that already carries `[待确认]` is handled by the tri-state scanner;
    the same claim must not be reported twice. Inline code / fences are ignored
    so documentation examples do not fail a real kit.
    """
    hits: list[int] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scan_line = INLINE_CODE_RE.sub("", line)
        if PENDING_TOKEN in scan_line:
            continue
        # NFKC folds full-width forms; removing whitespace catches "待 核 实".
        compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", scan_line))
        if "不确定度" in compact:
            # "保留不确定度词" is a rule about epistemic language, not a claim.
            continue
        if UNCERTAIN_SEMANTIC_RE.search(compact):
            hits.append(lineno)
    return hits


def _quote_from_marker(line: str) -> str:
    m = QUOTE_TEXT_RE.search(line)
    if not m:
        return ""
    return next((v for v in m.groupdict().values() if v), "").strip()


def _verify_pending_source(
    line: str,
    kit_dir: pathlib.Path,
    source_roots: list[pathlib.Path] | None = None,
) -> str:
    """Return "" when the marker's source is verifiable, else a reason code.

    Issue #15: previously only the literal words 原文/出处 were checked, so a
    fabricated `出处：fake.md:999` passed. Now a local source must exist, the line
    number must be in range, and the quoted text must appear near that line.
    URLs are accepted as external references (clickable) but not fetched here.
    Template shapes such as `<file>:<line>` stay exempt: they are documentation,
    not a claim about a real file.
    """
    m = SOURCE_REF_RE.search(line)
    if not m:
        return "PENDING_SOURCE_MISSING"
    src = m.group("src").strip().strip("`'\"“”「」[]() ")
    if not src:
        return "PENDING_SOURCE_MISSING"
    if src.startswith("<") or "<file>" in src:
        return ""
    if src.startswith(("http://", "https://")):
        return ""
    line_no: int | None = None
    path_part = src
    sm = SOURCE_LINE_RE.match(src)
    if sm:
        path_part = sm.group("path").strip()
        line_no = int(sm.group("line"))
    # Security: an explicit source must stay inside the kit dir or one of the
    # caller-approved --source-root dirs. Reject absolute paths, drive letters,
    # leading separators and `..` before touching the filesystem.
    if _ABS_REF_RE.match(path_part) or ".." in pathlib.PurePath(path_part).parts:
        return "PENDING_SOURCE_TRAVERSAL"
    roots = [kit_dir, *(source_roots or [])]
    target: pathlib.Path | None = None
    for root in roots:
        root_resolved = root.resolve()
        candidate = (root_resolved / path_part).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError:
            return "PENDING_SOURCE_TRAVERSAL"
        if candidate.is_file():
            target = candidate
            break
    if target is None:
        return "PENDING_SOURCE_MISSING"
    if line_no is not None:
        rows = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if line_no < 1 or line_no > len(rows):
            return "PENDING_SOURCE_LINE_OUT_OF_RANGE"
        quote = _quote_from_marker(line)
        if quote:
            # Allow ±1 line because exported chat files may put the same quote on
            # the adjacent line after a role/time prefix.
            window = "\n".join(rows[max(0, line_no - 2): min(len(rows), line_no + 1)])
            norm_quote = re.sub(r"\s+", "", unicodedata.normalize("NFKC", quote))
            norm_window = re.sub(r"\s+", "", unicodedata.normalize("NFKC", window))
            if norm_quote not in norm_window:
                return "PENDING_SOURCE_QUOTE_MISMATCH"
    return ""


def validate_kit(
    target_dir: pathlib.Path,
    strict: bool = False,
    forbidden_terms: list[str] | None = None,
    source_roots: list[pathlib.Path] | None = None,
) -> tuple[bool, list[str]]:
    """Return (passed, diagnostics) checking all 6 kit files under target_dir."""
    diagnostics: list[str] = []
    if not target_dir.is_dir():
        return False, [f"Target directory missing: {target_dir}"]

    passed = True
    compliant_total = 0

    for canonical in REQUIRED_KIT_FILES:
        fpath = find_kit_file(target_dir, canonical)
        if fpath is None:
            diagnostics.append(f"MISSING required file: {canonical}")
            passed = False
            continue
        fname = fpath.name
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
        compliant, bare_lines, pending_lines, compliant_lines = _scan_pending_markers(text)
        for lineno in compliant_lines:
            raw_line = text.splitlines()[lineno - 1]
            reason = _verify_pending_source(raw_line, target_dir, source_roots)
            if reason:
                diagnostics.append(f"{reason}: {fname}:{lineno}")
                passed = False
                compliant_total -= 1
        compliant_total += compliant
        for lineno in bare_lines:
            diagnostics.append(f"PENDING_UNTRACEABLE: {fname}:{lineno}")
            if strict:
                passed = False

        # Issue #2 Bug C: a claim written as "记不清 / 待核实 / 说不准" without a
        # [待确认] marker is still unresolved. Fail in both modes so it cannot
        # slip through as a finished fact.
        for lineno in _scan_uncertain_semantics(text):
            diagnostics.append(f"UNCERTAIN_SEMANTIC: {fname}:{lineno} (转成 [待确认] 并补原文/出处)")
            passed = False

        # Pending marker shape lines are exempt from the placeholder check: the
        # documented shape uses `<疑点>` / `<file>:<line>`, which PLACEHOLDER_RE
        # would otherwise flag as unfilled on an otherwise compliant marker.
        placeholders: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno in pending_lines:
                continue
            placeholders.extend(PLACEHOLDER_RE.findall(RUNTIME_VAR_RE.sub("", line)))
        if strict and placeholders:
            diagnostics.append(f"UNFILLED placeholders in {fname}: {placeholders[:5]}")
            passed = False

    if compliant_total > 0:
        diagnostics.append(
            f"INFO: {compliant_total} compliant '[待确认]' marker(s) pending backfill confirmation."
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
        "--source-root",
        action="append",
        default=[],
        type=pathlib.Path,
        help="额外目录：解析 [待确认] 的 出处：<file>:<line>（可多次传入）",
    )
    args = parser.parse_args()

    ok, msgs = validate_kit(
        args.target,
        strict=args.strict,
        forbidden_terms=args.forbidden,
        source_roots=args.source_root,
    )
    for m in msgs:
        print(m)
    print("VALIDATE_OK" if ok else "VALIDATE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
