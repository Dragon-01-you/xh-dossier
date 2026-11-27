#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ledger tests for `12_pipeline_audit.py` (issue #145).

Locks the promises from the spec:
- every row carries the fixed columns, including counter_version (口径版本);
- a failing step is still recorded, with a non-zero exit code;
- two runs are comparable: same step, same counter_version, different run_id;
- counting helpers never crash the pipeline.
"""

import importlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

audit = importlib.import_module("12_pipeline_audit")


def _rows(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_append_step_has_all_fixed_columns(tmp_path: pathlib.Path) -> None:
    ledger = tmp_path / "io_ledger.jsonl"
    row = audit.append_step(
        ledger, run_id="run-1", step="01_clean_and_index",
        input_count=3, output_count=10, new_count=7,
        actor="agent", exit_code=0, seconds=1.25, note="raw files -> db rows",
    )
    assert set(row) == set(audit.COLUMNS)
    assert row["counter_version"] == audit.COUNTER_VERSION
    assert _rows(ledger)[0]["new_count"] == 7


def test_failed_step_is_recorded_with_nonzero_exit(tmp_path: pathlib.Path) -> None:
    ledger = tmp_path / "io_ledger.jsonl"
    rc, row = audit.run_and_record(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        ledger=ledger, run_id="run-2", step="broken_step",
        input_count=1, output_count_fn=lambda: 1,
    )
    assert rc == 3
    assert row["exit_code"] == 3
    assert row["seconds"] > 0
    assert _rows(ledger)[-1]["step"] == "broken_step"


def test_two_runs_are_comparable(tmp_path: pathlib.Path) -> None:
    ledger = tmp_path / "io_ledger.jsonl"
    for run_id in ("run-a", "run-b"):
        audit.append_step(
            ledger, run_id=run_id, step="03_validate_kit",
            input_count=6, output_count=None, new_count=None,
            note="kit files validated",
        )
    rows = _rows(ledger)
    assert len(rows) == 2
    assert {row["run_id"] for row in rows} == {"run-a", "run-b"}
    assert {row["counter_version"] for row in rows} == {audit.COUNTER_VERSION}


def test_summarize_keeps_last_two_per_step(tmp_path: pathlib.Path) -> None:
    ledger = tmp_path / "io_ledger.jsonl"
    for i in range(3):
        audit.append_step(ledger, run_id=f"r{i}", step="same", input_count=i)
    report = audit.summarize(ledger)
    assert report["rows"] == 3
    assert len(report["steps"]["same"]) == 2


def test_counters_never_crash(tmp_path: pathlib.Path) -> None:
    assert audit.count_files(tmp_path / "missing") == 0
    assert audit.count_md(tmp_path / "missing") == 0
    assert audit.count_rows(tmp_path / "missing.db") is None
    assert audit.count_candidates(tmp_path / "missing") is None
