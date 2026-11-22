#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 4: Validate a 6-file AI onboarding kit for completeness, clichés, placeholders, and PII/local-path leaks."""

from __future__ import annotations

import argparse
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

# Accepted aliases for required files: real-world kits may ship a renamed
# sibling. Canonical name first; any present candidate satisfies the requirement.
FILE_ALIASES: dict[str, list[str]] = {
    "04-正反例避坑账.md": ["04-反面案例清单.md"],
}

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


# `[待确认]` provenance scanning (issue #15 / CONFLICT-05):
# - A compliant marker: `[待确认] <疑点> ｜ 原文：「…」 ｜ 出处：<file>:<line>`
#   whose cited file/line/quote really exist under the kit root -> INFO, never fails.
# - B unsourced marker: no `出处：` / `原文：` label -> PENDING_UNSOURCED.
# - C meta-rule reference inside inline backticks or a fenced code block -> ignored.
# Citation defect codes:
#   PENDING_SOURCE_TRAVERSAL  cited path escapes the kit root (absolute / `..` / drive)
#   PENDING_SOURCE_MISSING    cited file does not exist under the kit root
#   PENDING_LINE_OUT_OF_RANGE line number is below 1 or past the file's last line
#   PENDING_QUOTE_MISMATCH    normalized quote is not found on the cited line
PENDING_UNSOURCED = "PENDING_UNSOURCED"
PENDING_SOURCE_TRAVERSAL = "PENDING_SOURCE_TRAVERSAL"
PENDING_SOURCE_MISSING = "PENDING_SOURCE_MISSING"
PENDING_LINE_OUT_OF_RANGE = "PENDING_LINE_OUT_OF_RANGE"
PENDING_QUOTE_MISMATCH = "PENDING_QUOTE_MISMATCH"

INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FENCE_RE = re.compile(r"^\s*```")
PENDING_TOKEN = "[待确认]"
HAS_QUOTE_RE = re.compile(r"原文\s*[:：]")
HAS_SOURCE_RE = re.compile(r"出处\s*[:：]")
SOURCE_REF_RE = re.compile(r"出处\s*[:：]\s*(?P<ref>.+?)\s*(?:｜\s*|$)")
QUOTE_REF_RE = re.compile(r"原文\s*[:：]\s*(?P<quote>.+?)\s*(?:｜\s*|$)")
# `<file>:<line>` — last colon must carry a 1-based integer line number.
REF_SPLIT_RE = re.compile(r"^(?P<file>.+):(?P<line>\d+)$")
_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:|[\\/])")
_WRAP_QUOTES = "「」『』“”‘’\"'"


def _normalize_citation_text(text: str) -> str:
    """Normalize a quote / source line for comparison.

    NFKC unifies full-width vs half-width glyphs and common quote variants;
    surrounding CJK/ASCII wrap quotes are then stripped and all whitespace
    (spaces, tabs, full-width space, newlines) removed.
    """
    text = unicodedata.normalize("NFKC", text)
    for ch in _WRAP_QUOTES:
        text = text.replace(ch, "")
    return re.sub(r"\s+", "", text)


def _strip_wrap_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in _WRAP_QUOTES and text[-1] in _WRAP_QUOTES:
        text = text[1:-1]
    return text.strip()


def _strip_code_for_placeholders(line: str) -> str:
    """Remove real inline code/path spans before the placeholder check.

    A backtick span that opens with a `<...>` token is itself a template fill-in
    placeholder and must stay visible; a span carrying a path or command (e.g.
    `` `01-当前任务/<任务>/` ``) holds a runtime variable and is stripped.
    """

    def _sub(match: re.Match[str]) -> str:
        inner = match.group(0)[1:-1].strip()
        if inner.startswith("<"):
            return match.group(0)
        return ""

    return INLINE_CODE_RE.sub(_sub, line)


def _check_citation(kit_root: pathlib.Path, ref: str, quote: str) -> str | None:
    """Verify the cited file/line/quote really exist under the kit root.

    Return an error code, or ``None`` when the citation checks out.
    """
    ref = ref.strip()
    if not ref:
        return PENDING_SOURCE_MISSING

    # Reject absolute paths, drive letters, leading separators outright (traversal).
    if _ABSOLUTE_RE.match(ref):
        return PENDING_SOURCE_TRAVERSAL

    match = REF_SPLIT_RE.match(ref)
    if not match:
        # Cannot parse as <file>:<line> — the provenance is unusable.
        return PENDING_SOURCE_MISSING

    rel_file = match.group("file").strip()
    line_no = int(match.group("line"))

    # Defense in depth: reject explicit `..` segments even if resolution would stay inside root.
    if ".." in pathlib.PurePath(rel_file).parts:
        return PENDING_SOURCE_TRAVERSAL

    root = kit_root.resolve()
    candidate = (root / rel_file).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return PENDING_SOURCE_TRAVERSAL

    if not candidate.is_file():
        return PENDING_SOURCE_MISSING

    source_lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_no < 1 or line_no > len(source_lines):
        return PENDING_LINE_OUT_OF_RANGE

    if _normalize_citation_text(quote) not in _normalize_citation_text(source_lines[line_no - 1]):
        return PENDING_QUOTE_MISMATCH

    return None


def _scan_pending_markers(
    text: str, kit_root: pathlib.Path
) -> tuple[list[dict[str, object]], set[int]]:
    """Scan `[待确认]` markers and verify each one's provenance.

    Lines inside fenced code blocks and inline backtick spans are ignored (meta-rule
    references), matching the previous `` `[待确认]` `` exemption. Returns
    ``(records, pending_lines)`` where each record carries ``lineno`` and ``error``
    (``None`` when the marker is compliant).
    """
    records: list[dict[str, object]] = []
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

        error: str | None
        if not HAS_QUOTE_RE.search(scan_line) or not HAS_SOURCE_RE.search(scan_line):
            error = PENDING_UNSOURCED
        else:
            ref_match = SOURCE_REF_RE.search(scan_line)
            quote_match = QUOTE_REF_RE.search(scan_line)
            ref = ref_match.group("ref") if ref_match else ""
            quote = _strip_wrap_quotes(quote_match.group("quote")) if quote_match else ""
            error = _check_citation(kit_root, ref, quote)

        records.append({"lineno": lineno, "error": error})
    return records, pending_lines


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
    compliant_total = 0

    for canonical in REQUIRED_KIT_FILES:
        candidates = [canonical, *FILE_ALIASES.get(canonical, [])]
        fpath = next(
            (target_dir / name for name in candidates if (target_dir / name).is_file()),
            None,
        )
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

        # `[待确认]` provenance check (issue #15): compliant -> INFO;
        # unsourced / bad citation -> defect (fails under --strict); backtick/fence
        # meta references are ignored by _scan_pending_markers.
        records, pending_lines = _scan_pending_markers(text, target_dir)
        for record in records:
            lineno = int(record["lineno"])
            error = record["error"]
            if error is None:
                compliant_total += 1
            else:
                diagnostics.append(f"{error}: {fname}:{lineno}")
                if strict:
                    passed = False

        # Pending marker shape lines are exempt from the placeholder check: the
        # documented shape uses `<疑点>` / `<file>:<line>`, which PLACEHOLDER_RE
        # would otherwise flag as unfilled on an otherwise compliant marker.
        placeholders: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno in pending_lines:
                continue
            placeholders.extend(PLACEHOLDER_RE.findall(_strip_code_for_placeholders(line)))
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
        help="Fail on template placeholders or unsourced/invalid [待确认]; compliant markers stay INFO",
    )
    parser.add_argument("--forbidden", nargs="*", default=[], help="Extra personal terms that must not appear")
    args = parser.parse_args()

    ok, msgs = validate_kit(args.target, strict=args.strict, forbidden_terms=args.forbidden)
    for m in msgs:
        print(m)
    print("VALIDATE_OK" if ok else "VALIDATE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
