#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for `15_change_gate.py` — no before/after ledger, no merge."""

import importlib
import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
gate = importlib.import_module("15_change_gate")


def _record(before: dict, after: dict, diff_lines: list[str], status="modified",
            script="scripts/05b_l2_theme.py", marker="") -> str:
    def block(row: dict) -> str:
        return json.dumps(row, ensure_ascii=False)
    return (
        f"script: {script}\nstatus: {status}\n\n"
        f"## 改前\n\n{block(before)}\n\n"
        f"## 改后\n\n{block(after)}\n\n"
        f"## 差异\n\n" + "\n".join(f"- {ln}" for ln in diff_lines) + f"\n{marker}\n"
    )


def _diff_full(before: dict, after: dict) -> list[str]:
    lines = []
    for key in gate.LEDGER_KEYS:
        b, a = str(before[key]), str(after[key])
        lines.append(f"`{key}`: 无变化" if b == a else f"`{key}`: {b} → {a}")
    return lines


def _row(tag="1", inp=346, out=6, new=6, sec=1.2):
    return {
        "run_id": f"r-{tag}", "step": "05b_l2_theme", "counter_version": "v1",
        "input_count": inp, "output_count": out, "new_count": new,
        "actor": "main", "exit_code": 0, "seconds": sec,
        "timestamp": f"2026-11-27T10:0{tag}:00+08:00", "note": tag,
    }


def _write(tmp_path, text, name="0001-x.md"):
    rec_dir = tmp_path / "docs" / "changes"
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / name).write_text(text, encoding="utf-8")
    return rec_dir


def _changed(tmp_path, *paths):
    f = tmp_path / "changed.txt"
    f.write_text("\n".join(paths) + "\n", encoding="utf-8")
    return f


def test_pass_when_record_is_complete(tmp_path, monkeypatch):
    before, after = _row("1"), _row("2", out=4, new=4, sec=1.1)
    monkeypatch.setattr(gate, "RECORD_DIR", _write(
        tmp_path, _record(before, after, _diff_full(before, after)))
    )
    assert gate.run(_changed(tmp_path, "M\tscripts/05b_l2_theme.py").read_text(
        encoding="utf-8")) == 0


def test_fail_when_script_changed_without_record(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "RECORD_DIR", tmp_path / "docs" / "changes")
    try:
        gate.run("M\tscripts/05b_l2_theme.py\n")
    except gate.GateError as exc:
        assert "docs/changes" in str(exc)
    else:
        raise AssertionError("missing record must fail")


def test_fail_when_diff_line_missing(tmp_path, monkeypatch):
    before, after = _row("1"), _row("2", out=4)
    lines = _diff_full(before, after)[:-1]  # drop `note`
    monkeypatch.setattr(gate, "RECORD_DIR", _write(tmp_path, _record(before, after, lines)))
    try:
        gate.run("M\tscripts/05b_l2_theme.py\n")
    except gate.GateError as exc:
        assert "note" in str(exc)
    else:
        raise AssertionError("missing diff line must fail")


def test_fail_when_unchanged_field_not_marked(tmp_path, monkeypatch):
    before, after = _row("1"), _row("2", out=4)
    lines = _diff_full(before, after)
    lines[3] = "`input_count`: 346"  # no 无变化
    monkeypatch.setattr(gate, "RECORD_DIR", _write(tmp_path, _record(before, after, lines)))
    try:
        gate.run("M\tscripts/05b_l2_theme.py\n")
    except gate.GateError as exc:
        assert "无变化" in str(exc)
    else:
        raise AssertionError("blank unchanged field must fail")


def test_fail_when_counter_versions_differ(tmp_path, monkeypatch):
    before, after = _row("1"), _row("2", out=4)
    record = _record(before, after, _diff_full(before, after)).replace(
        '"counter_version": "v1"', '"counter_version": "v2"', 1)
    monkeypatch.setattr(gate, "RECORD_DIR", _write(tmp_path, record))
    try:
        gate.run("M\tscripts/05b_l2_theme.py\n")
    except gate.GateError as exc:
        assert "口径版本" in str(exc)
    else:
        raise AssertionError("cross-version comparison must fail")


def test_new_script_needs_marker(tmp_path, monkeypatch):
    before, after = _row("1", inp=0, out=0, new=None), _row("2", inp=0, out=0, new=None)
    record = _record(before, after, _diff_full(before, after), status="new",
                     script="scripts/15_change_gate.py")
    monkeypatch.setattr(gate, "RECORD_DIR", _write(tmp_path, record))
    try:
        gate.run("A\tscripts/15_change_gate.py\n")
    except gate.GateError as exc:
        assert "新增脚本" in str(exc)
    else:
        raise AssertionError("new script without marker must fail")

    monkeypatch.setattr(gate, "RECORD_DIR", _write(
        tmp_path,
        _record(before, after, _diff_full(before, after), status="new",
                script="scripts/15_change_gate.py", marker=gate.NEW_FILE_MARKER),
        name="0002-gate.md",
    ))
    assert gate.run("A\tscripts/15_change_gate.py\n") == 0


def test_no_script_changed_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "RECORD_DIR", tmp_path / "docs" / "changes")
    assert gate.run("M\tdocs/specs/reflow-v1.md\n") == 0

