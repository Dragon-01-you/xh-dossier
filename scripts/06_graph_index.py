#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.4 · Layer 3 Graph recall: rule-extracted entity–relation edges with bitemporal validity.

This is the missing 3rd recall axis from issue #5. It is deliberately *not* a
keyword-synonym map: the ``relations`` table stores typed directed edges
(``subject`` -``relation``-> ``object``) with provenance ``rec_id`` and a
bitemporal window, mirroring the Graphiti/Zep edge model.

Extraction honesty note (see PR body / docs): entities and edges are produced by
**rule patterns + co-occurrence**, not an LLM. Recall is not calibrated; sparse
patterns cover only a handful of Chinese relation templates. Future LLM extraction
would plug into the same ``relations`` table (``extractor='llm'``).

Schema (columns named to match issue #5 minimum contract):

    relations(subject, relation, object, valid_from, valid_to,
              trans_from, trans_to, t_invalid, fact_text, rec_id, ...)

Superseded edges are kept: ``valid_to`` / ``trans_to`` are closed and ``t_invalid``
is set to 1; the row is never deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sqlite3
import sys
from importlib import import_module
from typing import Any, Iterable

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_mod01 = import_module("01_clean_and_index")
_mod02 = import_module("02_four_way_match")
search_keyword = _mod01.search_keyword
NEGATION_MARKERS = _mod02.NEGATION_MARKERS

SELF_CANONICAL = "我（本人）"

QUOTED_RE = re.compile(r"[「『“\"'‘]([^「」『』“”\"'‘’\n]{2,20})[」』”\"'’]")
SPAN_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9#+.]{2,16}")

RELATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("LEARNS", re.compile(r"(?:我|本人)?(?:正在|在|开始)?学习\s*([\u4e00-\u9fa5A-Za-z0-9#+.]{2,16})")),
    ("PREPARES_FOR", re.compile(r"备考\s*([\u4e00-\u9fa5A-Za-z0-9#+.]{2,16})")),
    ("WORKS_AT", re.compile(r"(?:我|本人)?在\s*([\u4e00-\u9fa5A-Za-z0-9#+.]{2,16}?)\s*(?:工作|任职|上班)")),
    ("LIVES_IN", re.compile(r"(?:住在|搬到|定居在)\s*([\u4e00-\u9fa5A-Za-z0-9#+.]{2,16})")),
    ("LIKES", re.compile(r"(?:喜欢|偏好|偏爱|着迷于)\s*([\u4e00-\u9fa5A-Za-z0-9#+.]{2,16})")),
    ("RESPONSIBLE_FOR", re.compile(r"负责\s*([\u4e00-\u9fa5A-Za-z0-9#+.]{2,16})")),
    ("USES", re.compile(r"(?:使用|采用|用的是|在用)\s*([\u4e00-\u9fa5A-Za-z0-9#+.]{2,16})")),
]

TRIM_SUFFIX = ("这个", "那个", "一个", "一下", "方面", "东西", "的", "了", "过", "着")
STOP_OBJECTS = {"AI", "ai", "你", "他", "她", "它", "我们", "你们", "他们", "自己", "什么", "怎么", "这里", "那里"}

# Noise that must never become a graph node: hex colors, rgba(), CSS declarations,
# bare numbers, URLs, code punctuation. Rule extraction has no NER to separate
# these from real entities, so we reject them conservatively.
CODE_NOISE_RE = re.compile(
    r"^(#?[0-9a-fA-F]{3,8}"
    r"|rgba?\([^)]*\)"
    r"|[\w-]+\s*:\s*[^,;]+"
    r"|\d+(\.\d+)?%?"
    r"|https?://\S+)$"
)
NOISE_CHARS = set(":#();{}[]、，；")
MAX_COOCCUR_ENTITIES = 3

ENTITIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id      TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    entity_type    TEXT NOT NULL DEFAULT 'unknown',
    first_seen     TEXT
)
"""

RELATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS relations (
    rel_id       TEXT PRIMARY KEY,
    subject      TEXT NOT NULL,
    relation     TEXT NOT NULL,
    object       TEXT NOT NULL,
    valid_from   TEXT,
    valid_to     TEXT,
    trans_from   TEXT NOT NULL,
    trans_to     TEXT,
    t_invalid    INTEGER NOT NULL DEFAULT 0,
    fact_text    TEXT NOT NULL,
    rec_id       TEXT NOT NULL,
    extractor    TEXT NOT NULL DEFAULT 'rule',
    confidence   REAL NOT NULL DEFAULT 1.0,
    superseded_by TEXT,
    UNIQUE(subject, relation, object, rec_id)
)
"""


def _connect(db_path: pathlib.Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def ensure_graph_schema(con: sqlite3.Connection) -> None:
    con.execute(ENTITIES_TABLE_SQL)
    con.execute(RELATIONS_TABLE_SQL)
    con.execute("CREATE INDEX IF NOT EXISTS idx_rel_subj ON relations(subject)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rel_obj ON relations(object)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rel_valid ON relations(valid_from, valid_to)")
    con.commit()


PARTICLE_ONLY_RE = re.compile(r"^[的是了在和与我你他她它及或嘛呢吧啊呀哦]+$")


def _clean_span(span: str) -> str | None:
    text = span.strip()
    # Strip markdown bold/italic/heading/quote decorations and edge punctuation.
    text = text.strip("*#->·• ，。！？、,.!?：:;")
    for suffix in TRIM_SUFFIX:
        if text.endswith(suffix) and len(text) - len(suffix) >= 2:
            text = text[: -len(suffix)]
    text = text.strip("*#->·• ，。！？、,.!?：:;")
    if len(text) < 2 or len(text) > 16 or text in STOP_OBJECTS:
        return None
    if any(ch in text for ch in NOISE_CHARS):
        return None
    if "/" in text or "\\" in text or "http" in text.lower():
        return None
    if text[0] in "你我他她它":
        return None
    if CODE_NOISE_RE.match(text):
        return None
    if PARTICLE_ONLY_RE.match(text):
        return None
    # A node must carry a Chinese character or a Latin letter; bare symbols/digits fail.
    if not re.search(r"[\u4e00-\u9fa5]", text) and not re.search(r"[A-Za-z]", text):
        return None
    return text


def extract_entities(content: str, *, lexicon: Iterable[str] = ()) -> list[dict[str, str]]:
    """Rule-based entity candidates: self node, quoted spans, optional lexicon hits.

    This is a conservative NER stand-in, not a real named-entity recognizer.
    """
    found: dict[str, dict[str, str]] = {SELF_CANONICAL: {"canonical_name": SELF_CANONICAL, "entity_type": "self"}}
    for quoted in QUOTED_RE.findall(content):
        cleaned = _clean_span(quoted)
        if cleaned:
            found.setdefault(cleaned, {"canonical_name": cleaned, "entity_type": "quoted"})
    for term in lexicon:
        term = (term or "").strip()
        if term and term in content:
            found.setdefault(term, {"canonical_name": term, "entity_type": "lexicon"})
    return list(found.values())


def _clause_around(content: str, start: int, end: int) -> str:
    left = max(0, start - 12)
    right = min(len(content), end + 12)
    return content[left:right]


def extract_relations(
    content: str, entities: list[dict[str, str]], *, lexicon: Iterable[str] = ()
) -> tuple[list[dict[str, str]], int]:
    """Produce typed edges from fixed Chinese templates; negation clauses are skipped.

    Subject defaults to the self node. The captured object is linked to a quoted /
    lexicon entity when it matches, otherwise recorded as a generic ``span`` entity.
    Returns ``(edges, negation_skipped)``.
    """
    edges: list[dict[str, str]] = []
    negation_skipped = 0
    entity_names = {e["canonical_name"] for e in entities}

    for predicate, pattern in RELATION_PATTERNS:
        for match in pattern.finditer(content):
            clause = _clause_around(content, match.start(), match.end())
            if any(neg in clause for neg in NEGATION_MARKERS):
                negation_skipped += 1
                continue  # negation blindness guard: "先不要学习 X" must not become a LEARNS edge
            # Rule extraction has no real subject parser. Without a first-person cue
            # in the clause, do not silently attribute a third-person sentence to
            # 我（本人） (e.g. "Python 使用 ..." is not "I use Python").
            if "我" not in clause and "本人" not in clause:
                continue
            cleaned = _clean_span(match.group(1))
            if cleaned is None:
                continue
            object_name = cleaned
            for known in entity_names:
                if known != SELF_CANONICAL and (known in cleaned or cleaned in known):
                    object_name = known
                    break
            edges.append(
                {
                    "subject": SELF_CANONICAL,
                    "relation": predicate,
                    "object": object_name,
                    "fact_text": clause.replace("\n", " ").strip(),
                }
            )

    # Co-occurrence edges: entities mentioned in the same record -> MENTIONS.
    # This is a weak signal (window = one record), kept distinct from template edges.
    # Cap the per-record fan-out and skip substring pairs to avoid O(n^2) noise.
    mentioned = [name for name in entity_names if name != SELF_CANONICAL][:MAX_COOCCUR_ENTITIES]
    for i, left in enumerate(mentioned):
        for right in mentioned[i + 1 :]:
            if left in right or right in left:
                continue
            edges.append(
                {
                    "subject": left,
                    "relation": "MENTIONS",
                    "object": right,
                    "fact_text": content.replace("\n", " ").strip()[:160],
                }
            )
    return edges, negation_skipped


def _entity_id(name: str) -> str:
    return "ENT-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:10]


def _rel_id(rec_id: str, subject: str, relation: str, object_name: str) -> str:
    key = f"{rec_id}|{subject}|{relation}|{object_name}"
    return "REL-" + hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def build_graph(db_path: pathlib.Path, *, lexicon: Iterable[str] = (), rebuild: bool = False) -> dict[str, int]:
    """Extract entities + edges from ``records`` and store them in the derived tables.

    ``rebuild=True`` clears the derived graph tables first (index rebuild, not history
    invalidation); default is incremental ``INSERT OR IGNORE``.
    """
    con = _connect(db_path)
    try:
        ensure_graph_schema(con)
        has_records = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone()
        if not has_records:
            raise FileNotFoundError("records table not found; cannot build graph")
        if rebuild:
            con.execute("DELETE FROM relations")
            con.execute("DELETE FROM entities")
            con.commit()

        rows = con.execute("SELECT rec_id, created_at, role, content FROM records ORDER BY rec_id").fetchall()
        # #10: prefer the export's event_date for the graph's valid-time window;
        # fall back to created_at only for legacy rows without the column.
        record_cols = [r[1] for r in con.execute("PRAGMA table_info(records)").fetchall()]
        has_event_date = "event_date" in record_cols
        if has_event_date:
            rows = con.execute(
                "SELECT rec_id, created_at, event_date, role, content FROM records ORDER BY rec_id"
            ).fetchall()
        lex = list(lexicon)
        entity_count = 0
        edge_count = 0
        negation_skipped = 0
        for row in rows:
            content = row["content"] or ""
            event = (row["event_date"] or "").strip()[:10] if has_event_date else ""
            valid_date = event if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", event) else ""
            date = (valid_date or ((row["created_at"] or "")[:10] if not has_event_date else "")) or None
            trans_date = ((row["created_at"] or "")[:10] or date)
            entities = extract_entities(content, lexicon=lex)
            for ent in entities:
                cur = con.execute(
                    "INSERT OR IGNORE INTO entities (entity_id, canonical_name, entity_type, first_seen) VALUES (?, ?, ?, ?)",
                    (_entity_id(ent["canonical_name"]), ent["canonical_name"], ent["entity_type"], date),
                )
                if cur.rowcount:
                    entity_count += 1
            edges, skipped = extract_relations(content, entities, lexicon=lex)
            negation_skipped += skipped
            for edge in edges:
                # register a span entity for unmatched objects
                if edge["object"] not in {e["canonical_name"] for e in entities}:
                    con.execute(
                        "INSERT OR IGNORE INTO entities (entity_id, canonical_name, entity_type, first_seen) VALUES (?, ?, 'span', ?)",
                        (_entity_id(edge["object"]), edge["object"], date),
                    )
                rel_id = _rel_id(row["rec_id"], edge["subject"], edge["relation"], edge["object"])
                cur = con.execute(
                    """
                    INSERT OR IGNORE INTO relations
                        (rel_id, subject, relation, object, valid_from, valid_to,
                         trans_from, trans_to, t_invalid, fact_text, rec_id, extractor, confidence)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, 0, ?, ?, 'rule', 1.0)
                    """,
                    (rel_id, edge["subject"], edge["relation"], edge["object"], date, trans_date, edge["fact_text"], row["rec_id"]),
                )
                if cur.rowcount:
                    edge_count += 1
        con.commit()
        return {"records": len(rows), "entities": entity_count, "edges": edge_count, "negation_skipped": negation_skipped}
    finally:
        con.close()


def invalidate_relation(
    db_path: pathlib.Path,
    old_rel_id: str,
    new_rel_id: str,
    *,
    valid_to: str | None = None,
    trans_to: str | None = None,
) -> dict[str, Any]:
    """Close an old edge and point it at the replacement edge; history row preserved."""
    con = _connect(db_path)
    try:
        ensure_graph_schema(con)
        old = con.execute("SELECT * FROM relations WHERE rel_id=?", (old_rel_id,)).fetchone()
        if old is None:
            raise KeyError(f"relation not found: {old_rel_id}")
        new = con.execute("SELECT * FROM relations WHERE rel_id=?", (new_rel_id,)).fetchone()
        if new is None:
            raise KeyError(f"replacement relation not found: {new_rel_id}")
        end_date = valid_to or new["valid_from"]
        trans_end = trans_to or end_date
        con.execute(
            """
            UPDATE relations
               SET valid_to = ?, trans_to = ?, t_invalid = 1, superseded_by = ?
             WHERE rel_id = ? AND t_invalid = 0
            """,
            (end_date, trans_end, new_rel_id, old_rel_id),
        )
        con.commit()
        row = con.execute("SELECT * FROM relations WHERE rel_id=?", (old_rel_id,)).fetchone()
        return dict(row)
    finally:
        con.close()


def _resolve_entity(con: sqlite3.Connection, entity_name: str) -> str | None:
    target = entity_name.strip()
    exact = con.execute("SELECT canonical_name FROM entities WHERE canonical_name=?", (target,)).fetchone()
    if exact:
        return exact["canonical_name"]
    like = con.execute("SELECT canonical_name FROM entities WHERE canonical_name LIKE ? LIMIT 1", (f"%{target}%",)).fetchone()
    return like["canonical_name"] if like else None


def _active_edges(
    con: sqlite3.Connection,
    *,
    as_of: str | None,
    relation: str | None,
    since: str | None,
    until: str | None,
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[Any] = []
    # Current-state view hides superseded edges; a point-in-time view keeps edges
    # that were valid inside their own window (t_invalid marks replacement, not deletion).
    if as_of is None:
        where.append("t_invalid = 0")
    if relation:
        where.append("relation = ?")
        params.append(relation)
    if as_of:
        where.append("valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)")
        params.extend([as_of, as_of])
    if since:
        where.append("valid_from >= ?")
        params.append(since)
    if until:
        where.append("valid_from <= ?")
        params.append(until)
    sql = "SELECT * FROM relations"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY valid_from, rel_id"
    return con.execute(sql, params).fetchall()


def graph_neighbors(
    db_path: pathlib.Path,
    entity_name: str,
    *,
    hops: int = 1,
    as_of: str | None = None,
    relation: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """BFS neighborhood of ``entity_name`` over active edges (1 or 2 hops).

    Every returned edge carries its ``rec_id`` so the original record can be traced
    back. ``as_of`` filters edges by their valid-time window; an edge not yet valid at
    that date is excluded.
    """
    hops = max(1, min(2, hops))
    con = _connect(db_path)
    try:
        ensure_graph_schema(con)
        start = _resolve_entity(con, entity_name)
        if start is None:
            return []
        edges = _active_edges(con, as_of=as_of, relation=relation, since=since, until=until)

        adjacency: dict[str, list[sqlite3.Row]] = {}
        for edge in edges:
            adjacency.setdefault(edge["subject"], []).append(edge)
            adjacency.setdefault(edge["object"], []).append(edge)

        seen_edges: dict[str, int] = {}
        frontier = {start}
        visited = {start}
        for distance in range(1, hops + 1):
            next_frontier: set[str] = set()
            for node in frontier:
                for edge in adjacency.get(node, []):
                    other = edge["object"] if edge["subject"] == node else edge["subject"]
                    if edge["rel_id"] not in seen_edges:
                        seen_edges[edge["rel_id"]] = distance
                    if other not in visited:
                        next_frontier.add(other)
            visited |= next_frontier
            frontier = next_frontier
            if not frontier:
                break

        results: list[dict[str, Any]] = []
        for edge in edges:
            distance = seen_edges.get(edge["rel_id"])
            if distance is None or distance > hops:
                continue
            results.append(
                {
                    "distance": distance,
                    "subject": edge["subject"],
                    "relation": edge["relation"],
                    "object": edge["object"],
                    "valid_from": edge["valid_from"],
                    "valid_to": edge["valid_to"],
                    "t_invalid": edge["t_invalid"],
                    "fact_text": edge["fact_text"],
                    "rec_id": edge["rec_id"],
                }
            )
        results.sort(key=lambda r: (r["distance"], r["rec_id"]))
        return results[:limit]
    finally:
        con.close()


def query_relations(
    db_path: pathlib.Path,
    *,
    entity: str | None = None,
    relation: str | None = None,
    keyword: str | None = None,
    as_of: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Flat edge query with optional entity / predicate / FTS keyword + temporal filters."""
    con = _connect(db_path)
    try:
        ensure_graph_schema(con)
        edges = _active_edges(con, as_of=as_of, relation=relation, since=since, until=until)
        results: list[dict[str, Any]] = []
        kw_ids: set[str] | None = None
        if keyword:
            kw_ids = {h["rec_id"] for h in search_keyword(db_path, keyword, limit=limit * 5)}
        for edge in edges:
            if entity:
                target = entity.strip()
                if target not in edge["subject"] and target not in edge["object"]:
                    continue
            if kw_ids is not None and edge["rec_id"] not in kw_ids:
                continue
            results.append(
                {
                    "subject": edge["subject"],
                    "relation": edge["relation"],
                    "object": edge["object"],
                    "valid_from": edge["valid_from"],
                    "valid_to": edge["valid_to"],
                    "fact_text": edge["fact_text"],
                    "rec_id": edge["rec_id"],
                }
            )
        return results[:limit]
    finally:
        con.close()


def render_graph_markdown(rows: list[dict[str, Any]], *, entity_name: str) -> str:
    lines = [f"# Graph neighborhood: {entity_name}", "", f"> 命中 `{len(rows)}` 条边；每条带 `rec_id` 回溯原文。", ""]
    for r in rows:
        lines.append(
            f"- `[h{r['distance']} | {r['rec_id']} | {r.get('valid_from') or '?'}]` "
            f"{r['subject']} -`{r['relation']}`-> {r['object']} ｜ {r['fact_text'][:80].replace(chr(10), ' ')}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Layer 3 graph recall: rule-extracted entity–relation edges.")
    parser.add_argument("--db", required=True, type=pathlib.Path)
    parser.add_argument("--action", choices=["build", "neighbors", "recall"], default="recall")
    parser.add_argument("--entity", help="Entity name (node) for neighborhood / edge filter.")
    parser.add_argument("--relation", help="Predicate filter, e.g. LEARNS / WORKS_AT / MENTIONS.")
    parser.add_argument("--keyword", help="Optional FTS5 keyword combined with edge filter.")
    parser.add_argument("--hops", type=int, default=1, choices=[1, 2])
    parser.add_argument("--as-of", help="Point-in-time date YYYY-MM-DD (valid-time filter).")
    parser.add_argument("--since", help="Lower bound on valid_from.")
    parser.add_argument("--until", help="Upper bound on valid_from.")
    parser.add_argument("--lexicon", nargs="*", default=[], help="Explicit entity whitelist names.")
    parser.add_argument("--rebuild", action="store_true", help="Clear derived graph tables before rebuild.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.action == "build":
            stats = build_graph(args.db, lexicon=args.lexicon, rebuild=args.rebuild)
            print(f"GRAPH_BUILD {json.dumps(stats, ensure_ascii=False)}")
            if args.json:
                print(json.dumps(stats, ensure_ascii=False, indent=2))
            return 0

        if args.action == "neighbors":
            if not args.entity:
                print("NEIGHBORS_NEEDS: --entity is required")
                return 2
            rows = graph_neighbors(
                args.db, args.entity, hops=args.hops, as_of=args.as_of,
                relation=args.relation, since=args.since, until=args.until, limit=args.limit,
            )
            payload = {"entity": args.entity, "hops": args.hops, "count": len(rows), "rows": rows}
            print(f"GRAPH_NEIGHBORS {len(rows)} edge(s)")
            if not args.json:
                print(render_graph_markdown(rows, entity_name=args.entity))
        else:
            rows = query_relations(
                args.db, entity=args.entity, relation=args.relation, keyword=args.keyword,
                as_of=args.as_of, since=args.since, until=args.until, limit=args.limit,
            )
            payload = {"count": len(rows), "rows": rows}
            print(f"GRAPH_RECALL {len(rows)} edge(s)")

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    except FileNotFoundError as exc:
        print(f"DB_NOT_FOUND: {exc}")
        return 2
    except (KeyError, ValueError) as exc:
        print(f"GRAPH_INPUT_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
