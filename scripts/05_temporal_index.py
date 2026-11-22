#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.3 · Layer 4 Temporal recall: time-range filtering and point-in-time (``AS OF``) slicing.

This module adds the missing 4th recall axis described in issue #5. It works on top
of the existing ``records`` / ``records_fts`` tables and never rebuilds the old cold
archive: on a legacy database that only has ``records`` + ``records_fts``, the new
``fact_validity`` table is created automatically on first use; if the derived table
is still empty, queries fall back to filtering ``records.created_at`` directly.

Bitemporal model (aligned with Graphiti's real column semantics, see
``docs/design-retrieval-layer3-4.md``):

* World time ``T``: ``valid_from`` (fact started being true) / ``valid_to`` (fact
  stopped being true; ``NULL`` = open interval).
* Transaction time ``T'``: ``trans_from`` (system learned it) / ``trans_to``
  (system marked it superseded; ``NULL`` = still known).
* ``t_invalid`` is an explicit invalidation flag; superseded facts are kept, never
  deleted. ``superseded_by`` points at the replacing fact.

Honest data limitation: the current export carries a single date per record, so in
the backfill ``valid_from == trans_from == records.created_at``. The two clocks only
diverge once ``invalidate_fact`` writes a different ``trans_to`` (or future exports
carry both an event time and an ingestion time).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sqlite3
import sys
from importlib import import_module
from typing import Any, Iterable

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_mod01 = import_module("01_clean_and_index")
search_keyword = _mod01.search_keyword

DATE_RE = __import__("re").compile(r"^(\d{4})-(\d{2})-(\d{2})")

VALIDITY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fact_validity (
    fact_id       TEXT PRIMARY KEY,
    valid_from    TEXT NOT NULL,
    valid_to      TEXT,
    trans_from    TEXT NOT NULL,
    trans_to      TEXT,
    t_invalid     INTEGER NOT NULL DEFAULT 0,
    superseded_by TEXT,
    source_rec_id TEXT NOT NULL,
    note          TEXT
)
"""

CLOCK_COLUMNS = {
    "valid": ("valid_from", "valid_to"),
    "transaction": ("trans_from", "trans_to"),
}


def normalize_date(value: Any) -> str | None:
    """Normalize a stored date/ISO timestamp into a ``YYYY-MM-DD`` string.

    Returns ``None`` for ``None``, empty strings, ``unknown`` and any format that
    cannot be parsed as a real calendar date. A full ISO timestamp
    (``2026-11-18 17:50:21 +08:00``) is reduced to its date part. Never raises on
    malformed input.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return None
    match = DATE_RE.match(text)
    if not match:
        return None
    candidate = match.group(0)
    try:
        _dt.datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def _connect(db_path: pathlib.Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _records_table_exists(con: sqlite3.Connection) -> bool:
    row = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone()
    return row is not None


def ensure_temporal_schema(con: sqlite3.Connection) -> None:
    """Create ``fact_validity`` if missing. Safe to call on legacy databases."""
    con.execute(VALIDITY_TABLE_SQL)
    con.execute("CREATE INDEX IF NOT EXISTS idx_fv_valid ON fact_validity(valid_from, valid_to)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fv_trans ON fact_validity(trans_from, trans_to)")
    con.commit()


def backfill_from_records(db_path: pathlib.Path) -> dict[str, int]:
    """Mirror every parseable ``records.created_at`` row into ``fact_validity``.

    Idempotent: existing fact rows are left untouched (``INSERT OR IGNORE``). Rows
    with empty / unparsable dates are counted as ``skipped_bad_date`` and never
    written as dirty data. Does not rebuild or touch ``records``.
    """
    con = _connect(db_path)
    try:
        if not _records_table_exists(con):
            raise FileNotFoundError("records table not found; cannot backfill temporal facts")
        ensure_temporal_schema(con)
        cols = _record_columns(con)
        has_event_date = "event_date" in cols
        if has_event_date:
            rows = con.execute(
                "SELECT rec_id, created_at, event_date FROM records ORDER BY rec_id"
            ).fetchall()
        else:
            rows = con.execute("SELECT rec_id, created_at FROM records ORDER BY rec_id").fetchall()
        backfilled = 0
        skipped_bad_date = 0
        already = 0
        for row in rows:
            # #10 event time: valid_from uses the event date when the export has it;
            # trans_from stays the ingestion/mention date. A blank event_date falls
            # back to created_at so a legacy row is never silently dropped.
            event_date = normalize_date(row["event_date"]) if has_event_date else None
            ingested = normalize_date(row["created_at"])
            date = event_date or ingested
            if date is None:
                skipped_bad_date += 1
                continue
            trans_date = ingested or date
            cur = con.execute(
                """
                INSERT OR IGNORE INTO fact_validity
                    (fact_id, valid_from, valid_to, trans_from, trans_to,
                     t_invalid, superseded_by, source_rec_id, note)
                VALUES (?, ?, NULL, ?, NULL, 0, NULL, ?, ?)
                """,
                (
                    row["rec_id"],
                    date,
                    trans_date,
                    row["rec_id"],
                    "backfill: valid_from=event_date/created_at, trans_from=created_at",
                ),
            )
            if cur.rowcount == 0:
                already += 1
            else:
                backfilled += 1
        con.commit()
        return {
            "records": len(rows),
            "backfilled": backfilled,
            "already_present": already,
            "skipped_bad_date": skipped_bad_date,
        }
    finally:
        con.close()


def invalidate_fact(
    db_path: pathlib.Path,
    old_fact_id: str,
    new_fact_id: str,
    *,
    valid_to: str | None = None,
    trans_to: str | None = None,
) -> dict[str, Any]:
    """Mark ``old_fact_id`` superseded by ``new_fact_id`` without deleting history.

    Follows the Graphiti/Zep rule: the old edge keeps its row, ``valid_to`` defaults
    to the new fact's ``valid_from``, ``trans_to`` defaults to that same date,
    ``t_invalid`` is set to 1 and ``superseded_by`` points to the replacement.
    """
    con = _connect(db_path)
    try:
        ensure_temporal_schema(con)
        old = con.execute("SELECT * FROM fact_validity WHERE fact_id=?", (old_fact_id,)).fetchone()
        if old is None:
            raise KeyError(f"fact not found: {old_fact_id}")
        new = con.execute("SELECT * FROM fact_validity WHERE fact_id=?", (new_fact_id,)).fetchone()
        if new is None:
            raise KeyError(f"replacement fact not found: {new_fact_id}")

        end_date = normalize_date(valid_to) or new["valid_from"]
        trans_end = normalize_date(trans_to) or end_date
        con.execute(
            """
            UPDATE fact_validity
               SET valid_to = ?, trans_to = ?, t_invalid = 1, superseded_by = ?
             WHERE fact_id = ? AND t_invalid = 0
            """,
            (end_date, trans_end, new_fact_id, old_fact_id),
        )
        con.commit()
        row = con.execute("SELECT * FROM fact_validity WHERE fact_id=?", (old_fact_id,)).fetchone()
        return dict(row)
    finally:
        con.close()


def _record_columns(con: sqlite3.Connection) -> list[str]:
    return [r[1] for r in con.execute("PRAGMA table_info(records)").fetchall()]


def _fallback_record_query(
    con: sqlite3.Connection,
    *,
    since: str | None,
    until: str | None,
    as_of: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Legacy path: no derived facts yet, filter ``records.created_at`` directly."""
    where: list[str] = []
    params: list[Any] = []
    if as_of is not None:
        where.append("created_at <= ?")
        params.append(as_of)
    if since is not None:
        where.append("created_at >= ?")
        params.append(since)
    if until is not None:
        where.append("created_at <= ?")
        params.append(until)
    sql = "SELECT rec_id, source_file, created_at, role, content FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at, rec_id LIMIT ?"
    params.append(limit)
    rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _fact_rows_to_records(
    con: sqlite3.Connection,
    fact_rows: Iterable[sqlite3.Row],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in fact_rows:
        rec = con.execute(
            "SELECT rec_id, source_file, created_at, role, content FROM records WHERE rec_id=?",
            (f["source_rec_id"],),
        ).fetchone()
        item = dict(f)
        if rec is not None:
            item.update(dict(rec))
        out.append(item)
    return out


def query_as_of(
    db_path: pathlib.Path,
    as_of: str,
    *,
    clock: str = "valid",
    limit: int = 50,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Return facts that were *effective* at ``as_of`` under the chosen clock.

    ``clock="valid"`` answers "what was true in the world on that date";
    ``clock="transaction"`` answers "what had the system learned by that date".
    Invalidated facts are excluded. When ``fact_validity`` is empty (legacy DB that
    has not been backfilled yet), falls back to ``records.created_at <= as_of``.
    """
    point = normalize_date(as_of)
    if point is None:
        raise ValueError(f"invalid as-of date: {as_of!r}")
    if clock not in CLOCK_COLUMNS:
        raise ValueError(f"clock must be 'valid' or 'transaction', got {clock!r}")

    con = _connect(db_path)
    try:
        ensure_temporal_schema(con)
        count = con.execute("SELECT count(*) FROM fact_validity").fetchone()[0]
        if count == 0:
            rows = _fallback_record_query(con, since=None, until=None, as_of=point, limit=limit)
        else:
            start_col, end_col = CLOCK_COLUMNS[clock]
            # Visibility at a point in time is decided by the validity window, not by
            # the t_invalid flag: a superseded fact stays visible inside its own
            # [valid_from, valid_to) window. t_invalid only records that a row was
            # later replaced (history preservation, not deletion).
            facts = con.execute(
                f"""
                SELECT * FROM fact_validity
                 WHERE {start_col} <= ?
                   AND ({end_col} IS NULL OR {end_col} > ?)
                 ORDER BY {start_col}, fact_id
                 LIMIT ?
                """,
                (point, point, limit),
            ).fetchall()
            rows = _fact_rows_to_records(con, facts)
        if keyword:
            kw_ids = {h["rec_id"] for h in search_keyword(db_path, keyword, limit=limit * 5)}
            rows = [r for r in rows if r["rec_id"] in kw_ids]
        return rows
    finally:
        con.close()


def query_time_range(
    db_path: pathlib.Path,
    since: str | None = None,
    until: str | None = None,
    *,
    clock: str = "valid",
    limit: int = 100,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Return current facts whose start date falls inside ``[since, until]``.

    The cold archive stores chat turns as point events on ``created_at``, so the
    range axis filters the fact's start date (``valid_from`` / ``trans_from``)
    inclusively on both ends. Persistent-fact interval overlap is the AS OF path
    (:func:`query_as_of`). Superseded rows (``t_invalid = 1``) are excluded from
    this current-state view; their history remains queryable point-in-time.
    """
    start = normalize_date(since) if since else None
    end = normalize_date(until) if until else None
    if clock not in CLOCK_COLUMNS:
        raise ValueError(f"clock must be 'valid' or 'transaction', got {clock!r}")

    con = _connect(db_path)
    try:
        ensure_temporal_schema(con)
        count = con.execute("SELECT count(*) FROM fact_validity").fetchone()[0]
        if count == 0:
            rows = _fallback_record_query(con, since=start, until=end, as_of=None, limit=limit)
        else:
            start_col, _end_col = CLOCK_COLUMNS[clock]
            where = ["t_invalid = 0"]
            params: list[Any] = []
            if start is not None:
                where.append(f"{start_col} >= ?")
                params.append(start)
            if end is not None:
                where.append(f"{start_col} <= ?")
                params.append(end)
            facts = con.execute(
                f"SELECT * FROM fact_validity WHERE {' AND '.join(where)} "
                f"ORDER BY {start_col}, fact_id LIMIT ?",
                (*params, limit),
            ).fetchall()
            rows = _fact_rows_to_records(con, facts)
        if keyword:
            kw_ids = {h["rec_id"] for h in search_keyword(db_path, keyword, limit=limit * 5)}
            rows = [r for r in rows if r["rec_id"] in kw_ids]
        return rows
    finally:
        con.close()


def render_temporal_markdown(rows: list[dict[str, Any]], *, title: str) -> str:
    """Human-auditable text rendering; provenance ``[REC-xxxx | date]`` preserved."""
    lines = [f"# {title}", "", f"> 命中 `{len(rows)}` 条；每条均带 `[REC-xxxx]` 可回溯原文。", ""]
    for r in rows:
        date = r.get("created_at") or r.get("valid_from") or "?"
        excerpt = (r.get("content") or r.get("fact_text") or "").replace("\n", " ")[:100]
        lines.append(f"- `[{r.get('rec_id', r.get('fact_id'))} | {date}]` {excerpt}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Layer 4 temporal recall: range filter + AS OF slice.")
    parser.add_argument("--db", required=True, type=pathlib.Path, help="Existing SQLite DB (records/records_fts).")
    parser.add_argument("--action", choices=["backfill", "as-of", "range", "invalidate"], default="range")
    parser.add_argument("--since", help="Lower bound date YYYY-MM-DD (inclusive).")
    parser.add_argument("--until", help="Upper bound date YYYY-MM-DD (inclusive).")
    parser.add_argument("--as-of", help="Point-in-time date YYYY-MM-DD.")
    parser.add_argument("--clock", choices=["valid", "transaction"], default="valid")
    parser.add_argument("--keyword", help="Optional FTS5 keyword combined with the temporal filter.")
    parser.add_argument("--old-fact", help="(invalidate) fact id being superseded.")
    parser.add_argument("--new-fact", help="(invalidate) replacement fact id.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown text.")
    args = parser.parse_args()

    try:
        if args.action == "backfill":
            stats = backfill_from_records(args.db)
            payload: Any = stats
            print(f"TEMPORAL_BACKFILL {json.dumps(stats, ensure_ascii=False)}")
        elif args.action == "invalidate":
            if not args.old_fact or not args.new_fact:
                print("INVALIDATE_NEEDS: --old-fact and --new-fact are required")
                return 2
            row = invalidate_fact(args.db, args.old_fact, args.new_fact)
            payload = row
            print(f"FACT_INVALIDATED {json.dumps(row, ensure_ascii=False)}")
        elif args.action == "as-of":
            if not args.as_of:
                print("AS_OF_NEEDS: --as-of is required")
                return 2
            rows = query_as_of(args.db, args.as_of, clock=args.clock, limit=args.limit, keyword=args.keyword)
            payload = {"as_of": args.as_of, "clock": args.clock, "count": len(rows), "rows": rows}
            print(f"AS_OF {len(rows)} row(s)")
            if not args.json:
                print(render_temporal_markdown(rows, title=f"Temporal slice AS OF {args.as_of} ({args.clock})"))
        else:
            rows = query_time_range(
                args.db, since=args.since, until=args.until, clock=args.clock,
                limit=args.limit, keyword=args.keyword,
            )
            payload = {"since": args.since, "until": args.until, "clock": args.clock, "count": len(rows), "rows": rows}
            print(f"TIME_RANGE {len(rows)} row(s)")
            if not args.json:
                print(render_temporal_markdown(rows, title=f"Temporal range {args.since} .. {args.until}"))

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    except FileNotFoundError as exc:
        print(f"DB_NOT_FOUND: {exc}")
        return 2
    except (KeyError, ValueError) as exc:
        print(f"TEMPORAL_INPUT_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
