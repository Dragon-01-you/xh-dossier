#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Change gate: any change to `scripts/*.py` must ship a before/after ledger.

Why this exists
---------------
"我优化了" is not evidence. A change to a pipeline script has to show two
ledger lines — 改前 and 改后 — under the same `counter_version`, plus an
explicit "无变化" for every field that did not move. Blank fields fail.

Usage
-----
    git diff --name-status origin/reflow-v1...HEAD > /tmp/changed.txt
    python -X utf8 scripts/15_change_gate.py --changed /tmp/changed.txt

`--changed` lines are `<STATUS>\t<path>`, as produced by `git diff --name-status`.
Records live in `docs/changes/*.md`; each record names one script.

Exit codes: 0 pass, 1 gate failed, 2 usage/input error.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

LEDGER_KEYS = (
    "run_id", "step", "counter_version", "input_count", "output_count",
    "new_count", "actor", "exit_code", "seconds", "timestamp", "note",
)
SCRIPTS_DIR = "scripts/"
RECORD_DIR = pathlib.Path("docs/changes")
NEW_FILE_MARKER = "新增脚本，无改前基线"
DIFF_LINE_RE = re.compile(r"^[-*]\s+`?([a-z_]+)`?\s*[:：]\s*(.*)$")


class GateError(Exception):
    """A record is missing or inconsistent. Message names the failing step."""


def parse_record(text: str) -> dict:
    """Parse one `docs/changes/*.md` record into script/status/before/after/diff."""
    script = re.search(r"^script:\s*`?([^`\s]+)`?", text, re.MULTILINE)
    status = re.search(r"^status:\s*`?([a-z]+)`?", text, re.MULTILINE)
    if not script or not status:
        raise GateError("记录缺 `script:` 或 `status:` 头")
    before = _json_block(text, "改前")
    after = _json_block(text, "改后")
    diff = _diff_section(text)
    return {
        "raw": text,
        "script": script.group(1),
        "status": status.group(1),
        "before": before,
        "after": after,
        "diff": diff,
    }


def _json_block(text: str, heading: str) -> dict:
    m = re.search(rf"^##\s+{heading}\s*$\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise GateError(f"缺少 `## {heading}` 段")
    body = m.group(1).strip()
    line = next((ln for ln in body.splitlines() if ln.strip().startswith("{")), None)
    if line is None:
        raise GateError(f"`## {heading}` 段没有台账行（应为一行 JSON）")
    try:
        row = json.loads(line)
    except json.JSONDecodeError as exc:
        raise GateError(f"`## {heading}` 台账行不是合法 JSON：{exc}") from exc
    missing = [k for k in LEDGER_KEYS if k not in row or row[k] == ""]
    if missing:
        raise GateError(f"`## {heading}` 台账行缺字段或留空：{','.join(missing)}")
    return row


def _diff_section(text: str) -> dict[str, str]:
    m = re.search(r"^##\s+差异\s*$\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise GateError("缺少 `## 差异` 段：没变化的字段必须显式写“无变化”")
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        hit = DIFF_LINE_RE.match(line.strip())
        if hit:
            out[hit.group(1)] = hit.group(2).strip()
    return out


def _text(value) -> str:
    """None renders as `null`, so a JSON null compares like the diff line says."""
    return "null" if value is None else str(value)


def check_record(record: dict) -> None:
    """Raise GateError when the record is unusable; print the summary otherwise."""
    step = record["script"]
    before, after, diff = record["before"], record["after"], record["diff"]
    if before["step"] != after["step"]:
        raise GateError(f"[{step}] 两行台账的 step 不一致：{before['step']} vs {after['step']}")
    if before["counter_version"] != after["counter_version"]:
        raise GateError(
            f"[{step}] 两行台账口径版本不同（{before['counter_version']} vs "
            f"{after['counter_version']}），跨口径不可比"
        )
    is_new = record["status"] == "new"
    if is_new and NEW_FILE_MARKER not in record["raw"]:
        raise GateError(f"[{step}] 新增脚本必须在 record 中写明“{NEW_FILE_MARKER}”")
    missing = [k for k in LEDGER_KEYS if k not in diff]
    if missing:
        raise GateError(f"[{step}] `## 差异` 缺这些字段：{','.join(missing)}（留空视为不通过）")

    changed = 0
    for key in LEDGER_KEYS:
        b, a = _text(before[key]), _text(after[key])
        line = diff[key]
        if b == a:
            if "无变化" not in line:
                raise GateError(f"[{step}] 字段 `{key}` 两行相同，但差异行没写“无变化”")
            continue
        changed += 1
        if b not in line or a not in line:
            raise GateError(f"[{step}] 字段 `{key}` 差异行没写清改前/改后：{b} → {a}")
    if changed == 0 and not is_new:
        raise GateError(f"[{step}] 两行台账完全相同：这次改动没有任何可核对的变化")


def changed_scripts(changed_text: str) -> list[tuple[str, str]]:
    """Return (status, path) for changed pipeline scripts, ignoring tests."""
    out: list[tuple[str, str]] = []
    for raw in changed_text.splitlines():
        parts = raw.strip().split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        if not path.startswith(SCRIPTS_DIR) or not path.endswith(".py"):
            continue
        if status.startswith("D"):
            continue
        out.append((status[0], path))
    return out


def load_records() -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not RECORD_DIR.is_dir():
        return records
    for path in sorted(RECORD_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        # READMEs embed the format inside fenced blocks; those are examples,
        # not records.
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        if not re.search(r"^script:\s*`?([^`\s]+)`?", text, re.MULTILINE):
            continue
        try:
            rec = parse_record(text)
        except GateError as exc:
            raise GateError(f"{path}: {exc}") from exc
        rec["path"] = str(path)
        records[rec["script"]] = rec
    return records


def run(changed_text: str) -> int:
    scripts = changed_scripts(changed_text)
    if not scripts:
        print("CHANGE_GATE_OK no script changed")
        return 0
    records = load_records()
    for status, path in scripts:
        rec = records.get(path)
        if rec is None:
            raise GateError(
                f"[{path}] 改了脚本但没有改前/改后台账：在 docs/changes/ 新增一条记录"
            )
        if status == "A" and rec["status"] != "new":
            raise GateError(f"[{path}] 新增脚本但记录 status={rec['status']}，应为 new")
        if status == "M" and rec["status"] not in ("modified", "new"):
            raise GateError(f"[{path}] 记录 status={rec['status']}，改脚本应为 modified")
        check_record(rec)
        print(f"CHANGE_GATE_OK {path} record={rec['path']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Require before/after ledger for script changes.")
    ap.add_argument("--changed", type=pathlib.Path, required=True,
                    help="git diff --name-status output")
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."),
                    help="repo root (records resolved from here)")
    args = ap.parse_args(argv)
    if not args.changed.is_file():
        print(f"CHANGE_GATE_ERROR: 找不到变更清单 {args.changed}", file=sys.stderr)
        return 2
    global RECORD_DIR
    RECORD_DIR = args.root / RECORD_DIR
    try:
        return run(args.changed.read_text(encoding="utf-8"))
    except GateError as exc:
        print(f"CHANGE_GATE_FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
