#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unified Layer 3 (graph) + Layer 4 (temporal) recall entry point for issue #5.

Combines the two new recall axes with the existing FTS5 keyword road:

* ``temporal`` — ``--since`` / ``--until`` range overlap, or ``--as-of`` point-in-time slice.
* ``graph``   — ``--entity`` neighborhood (1/2 hops) or ``--relation`` predicate filter.
* ``keyword`` — existing FTS5 trigram search, combinable with either axis.

Works on a legacy database that only has ``records`` / ``records_fts``: derived
tables are created automatically, and when they are still empty the temporal path
falls back to filtering ``records.created_at`` directly. No rebuild of the cold
archive is required.

Examples
--------
    python scripts/07_recall_time_graph.py --db work/real.db --since 2026-05-01 --until 2026-05-31
    python scripts/07_recall_time_graph.py --db work/real.db --as-of 2026-10-01 --keyword 验收 --json
    python scripts/07_recall_time_graph.py --db work/real.db --entity "Python" --hops 2 --relation LEARNS
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from importlib import import_module

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_mod01 = import_module("01_clean_and_index")
_mod05 = import_module("05_temporal_index")
_mod06 = import_module("06_graph_index")
search_keyword = _mod01.search_keyword


def run_recall(
    db_path: pathlib.Path,
    *,
    since: str | None = None,
    until: str | None = None,
    as_of: str | None = None,
    entity: str | None = None,
    relation: str | None = None,
    keyword: str | None = None,
    hops: int = 1,
    clock: str = "valid",
    limit: int = 50,
) -> dict:
    """Run temporal + graph + keyword recall and return a structured combined report."""
    report: dict = {"temporal": [], "graph": [], "keyword": []}

    # Temporal road (Layer 4) — only when the caller actually asked for a time axis.
    # An unfiltered temporal query would return every record and inflate counts.
    if as_of or since or until:
        if as_of:
            report["temporal"] = _mod05.query_as_of(
                db_path, as_of, clock=clock, limit=limit, keyword=keyword
            )
        else:
            report["temporal"] = _mod05.query_time_range(
                db_path, since=since, until=until, clock=clock, limit=limit, keyword=keyword
            )

    # Graph road (Layer 3) — only when an entity or predicate was requested.
    # A bare keyword belongs to the FTS road; it must not turn into "all edges".
    if entity or relation:
        if entity:
            report["graph"] = _mod06.graph_neighbors(
                db_path, entity, hops=hops, as_of=as_of, relation=relation,
                since=since, until=until, limit=limit,
            )
        else:
            report["graph"] = _mod06.query_relations(
                db_path, entity=entity, relation=relation, keyword=keyword,
                as_of=as_of, since=since, until=until, limit=limit,
            )

    # Existing FTS5 keyword road (Layer 1), kept separate for provenance.
    if keyword:
        report["keyword"] = search_keyword(db_path, keyword, limit=limit)

    report["counts"] = {
        "temporal": len(report["temporal"]),
        "graph": len(report["graph"]),
        "keyword": len(report["keyword"]),
    }
    return report


def _render_text(report: dict) -> str:
    lines = ["# Layer 3+4 合并召回（graph + temporal，叠加 FTS 关键词）", ""]
    counts = report["counts"]
    lines.append(f"> temporal `{counts['temporal']}` ｜ graph `{counts['graph']}` ｜ keyword `{counts['keyword']}`")
    lines.append("")
    lines.append("## Temporal 命中")
    for r in report["temporal"][:10]:
        lines.append(f"- `[{r.get('rec_id')} | {r.get('created_at') or r.get('valid_from')}]` {str(r.get('content', ''))[:80]}")
    lines.append("")
    lines.append("## Graph 命中")
    for e in report["graph"][:10]:
        lines.append(f"- `[h{e.get('distance', '-')} | {e.get('rec_id')}]` {e['subject']} -`{e['relation']}`-> {e['object']}")
    lines.append("")
    lines.append("## Keyword 命中（FTS5）")
    for k in report["keyword"][:10]:
        lines.append(f"- `[{k['rec_id']} | {k['created_at']}]` {k['content'][:80]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Combined graph + temporal recall over the cold archive.")
    parser.add_argument("--db", required=True, type=pathlib.Path, help="Existing SQLite DB (records/records_fts).")
    parser.add_argument("--action", choices=["recall", "build"], default="recall")
    parser.add_argument("--since", help="Temporal lower bound YYYY-MM-DD (inclusive).")
    parser.add_argument("--until", help="Temporal upper bound YYYY-MM-DD (inclusive).")
    parser.add_argument("--as-of", help="Point-in-time date YYYY-MM-DD (valid-time slice).")
    parser.add_argument("--entity", help="Graph node name for neighborhood lookup.")
    parser.add_argument("--relation", help="Graph predicate filter, e.g. LEARNS / MENTIONS.")
    parser.add_argument("--keyword", help="FTS5 keyword combined with temporal / graph filters.")
    parser.add_argument("--hops", type=int, default=1, choices=[1, 2])
    parser.add_argument("--clock", choices=["valid", "transaction"], default="valid")
    parser.add_argument("--lexicon", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args()

    try:
        if args.action == "build":
            temporal_stats = _mod05.backfill_from_records(args.db)
            graph_stats = _mod06.build_graph(args.db, lexicon=args.lexicon, rebuild=True)
            payload = {"temporal": temporal_stats, "graph": graph_stats}
            print(f"RECALL_BUILD {json.dumps(payload, ensure_ascii=False)}")
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        report = run_recall(
            args.db,
            since=args.since, until=args.until, as_of=args.as_of,
            entity=args.entity, relation=args.relation, keyword=args.keyword,
            hops=args.hops, clock=args.clock, limit=args.limit,
        )
        print(f"RECALL_OK temporal={report['counts']['temporal']} graph={report['counts']['graph']} keyword={report['counts']['keyword']}")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print(_render_text(report))
        return 0
    except FileNotFoundError as exc:
        print(f"DB_NOT_FOUND: {exc}")
        return 2
    except (KeyError, ValueError) as exc:
        print(f"RECALL_INPUT_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
