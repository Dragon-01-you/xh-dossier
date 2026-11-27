#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pipeline audit ledger (issue #145, parent spec #143).

One line per pipeline step, appended to a JSONL file, so anyone can answer
"what went in, what came out, what actually changed" without reading code.

Fixed columns (spec §监控):

    run_id / step / counter_version / input_count / output_count /
    new_count / actor / exit_code / seconds / timestamp / note

`counter_version` is the "口径版本": when a counter definition changes, bump it.
Rows with different versions are recorded but never compared for good-or-bad.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

DEFAULT_LEDGER = pathlib.Path("work") / "io_ledger.jsonl"
COUNTER_VERSION = "v1"
COLUMNS = (
    "run_id",
    "step",
    "counter_version",
    "input_count",
    "output_count",
    "new_count",
    "actor",
    "exit_code",
    "seconds",
    "timestamp",
    "note",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def append_step(
    ledger: pathlib.Path,
    *,
    run_id: str,
    step: str,
    input_count: int | None = None,
    output_count: int | None = None,
    new_count: int | None = None,
    actor: str = "agent",
    exit_code: int = 0,
    seconds: float = 0.0,
    note: str = "",
    counter_version: str = COUNTER_VERSION,
) -> dict:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "run_id": run_id,
        "step": step,
        "counter_version": counter_version,
        "input_count": input_count,
        "output_count": output_count,
        "new_count": new_count,
        "actor": actor,
        "exit_code": exit_code,
        "seconds": round(float(seconds), 3),
        "timestamp": now_iso(),
        "note": note,
    }
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def run_and_record(
    cmd: list[str],
    *,
    ledger: pathlib.Path,
    run_id: str,
    step: str,
    input_count: int | None = None,
    output_count_fn=None,
    actor: str = "agent",
    note: str = "",
    cwd: pathlib.Path | None = None,
    same_unit: bool = True,
) -> tuple[int, dict]:
    """Run one step, time it, record exit code and counts, never hide failures.

    ``same_unit=False`` when input and output are counted in different units
    (db rows vs kit files): ``new_count`` is then left null instead of
    subtracting apples from oranges.
    """
    t0 = time.monotonic()
    rc = subprocess.call(cmd, cwd=str(cwd) if cwd else None)
    seconds = time.monotonic() - t0
    output_count = None
    if output_count_fn is not None:
        try:
            output_count = output_count_fn()
        except Exception:  # a broken counter must not hide the step result
            output_count = None
            note = (note + " counter_failed").strip()
    new_count = None
    if same_unit and input_count is not None and output_count is not None:
        new_count = output_count - input_count
    row = append_step(
        ledger,
        run_id=run_id,
        step=step,
        input_count=input_count,
        output_count=output_count,
        new_count=new_count,
        actor=actor,
        exit_code=rc,
        seconds=seconds,
        note=note,
    )
    return rc, row


def count_files(folder: pathlib.Path, suffixes=(".md", ".json", ".txt", ".zip")) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)


def count_md(folder: pathlib.Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.glob("*.md") if p.is_file())


def count_rows(db: pathlib.Path) -> int | None:
    if not db.is_file():
        return None
    try:
        import sqlite3

        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT COUNT(*) FROM records").fetchone()
        return int(row[0]) if row else None
    except Exception:
        return None


def count_candidates(l2_dir: pathlib.Path) -> int | None:
    """Number of `### L2-xxxx` blocks in the generated candidate report."""
    note_file = l2_dir / "l2_candidates.md"
    if not note_file.is_file():
        return None
    return sum(1 for line in note_file.read_text(encoding="utf-8", errors="replace").splitlines()
               if line.startswith("### L2-"))


def read_ledger(ledger: pathlib.Path) -> list[dict]:
    if not ledger.is_file():
        return []
    rows = []
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize(ledger: pathlib.Path) -> dict:
    rows = read_ledger(ledger)
    by_step: dict[str, list[dict]] = {}
    for row in rows:
        by_step.setdefault(str(row.get("step")), []).append(row)
    return {
        "ledger": str(ledger),
        "rows": len(rows),
        "steps": {step: entries[-2:] for step, entries in by_step.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Show a pipeline audit ledger.")
    ap.add_argument("--ledger", type=pathlib.Path, default=DEFAULT_LEDGER)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = summarize(args.ledger)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"LEDGER {report['ledger']} rows={report['rows']}")
    for step, entries in report["steps"].items():
        for row in entries:
            print(
                f"  {row.get('run_id')} {step} "
                f"in={row.get('input_count')} out={row.get('output_count')} "
                f"new={row.get('new_count')} rc={row.get('exit_code')} "
                f"{row.get('seconds')}s {row.get('counter_version')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
