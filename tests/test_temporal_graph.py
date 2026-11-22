# -*- coding: utf-8 -*-
"""Issue #5: Layer 3 graph recall + Layer 4 temporal recall tests.

Covers: date normalization, backfill mapping, legacy-DB degradation, AS OF
effective/invalidated facts, t_invalid history preservation, dual-clock divergence,
range overlap boundaries, corrupted ``created_at`` tolerance, empty results, graph
negation guardrail, one/two-hop provenance, graph valid-time filter, and keyword
+temporal combination. Existing ``tests/test_pipeline.py`` is untouched.
"""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import sys
from importlib import import_module

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

mod01 = import_module("01_clean_and_index")
mod05 = import_module("05_temporal_index")
mod06 = import_module("06_graph_index")
mod07 = import_module("07_recall_time_graph")


def _make_db(
    tmp_path: pathlib.Path,
    records: list[tuple[str, str, str, str]],
    event_dates: dict[str, str] | None = None,
) -> pathlib.Path:
    """Build a minimal legacy-style DB with only ``records`` + ``records_fts``."""
    db_path = tmp_path / "recall.db"
    con = sqlite3.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE records (
            rec_id TEXT PRIMARY KEY, source_file TEXT NOT NULL, created_at TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, md5 TEXT NOT NULL UNIQUE
        )
        """
    )
    con.execute("CREATE VIRTUAL TABLE records_fts USING fts5(rec_id UNINDEXED, content, tokenize='trigram')")
    for rec_id, date, role, content in records:
        digest = hashlib.md5(content.encode("utf-8")).hexdigest()
        con.execute(
            "INSERT INTO records (rec_id, source_file, created_at, role, content, md5) VALUES (?, ?, ?, ?, ?, ?)",
            (rec_id, "f.md", date, role, content, digest),
        )
        con.execute("INSERT INTO records_fts (rec_id, content) VALUES (?, ?)", (rec_id, content))
    if event_dates:
        con.execute("ALTER TABLE records ADD COLUMN event_date TEXT")
        con.execute("ALTER TABLE records ADD COLUMN date_kind TEXT")
        for rec_id, event_date in event_dates.items():
            con.execute(
                "UPDATE records SET event_date=?, date_kind='stated' WHERE rec_id=?",
                (event_date, rec_id),
            )
    con.commit()
    con.close()
    return db_path


# --------------------------------------------------------------------------- #
# 1. Date normalization: real dates, ISO timestamps, empty / unknown / garbage
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-11-18", "2026-11-18"),
        ("2026-11-18 17:50:21 +08:00", "2026-11-18"),
        ("2026-11-18T17:50:21", "2026-11-18"),
        (None, None),
        ("", None),
        ("   ", None),
        ("unknown", None),
        ("2026/11/18", None),
        ("2026-13-40", None),  # real calendar date must validate
        ("not-a-date", None),
    ],
)
def test_normalize_date_boundaries(raw: str | None, expected: str | None) -> None:
    assert mod05.normalize_date(raw) == expected


# --------------------------------------------------------------------------- #
# 2. Backfill mirrors created_at onto both clocks; bad dates are skipped, not written
# --------------------------------------------------------------------------- #
def test_backfill_maps_created_at_both_clocks_and_skips_bad_date(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-02-25", "user", "第一条正常记录用于时间回填"),
            ("R2", "2026-09-13", "assistant", "第二条正常记录同样需要回填"),
            ("R3", "unknown", "user", "这条日期缺失，必须计入 skipped 而不是写脏数据"),
            ("R4", "", "user", "空日期行同样不能崩"),
        ],
    )
    stats = mod05.backfill_from_records(db)
    assert stats["records"] == 4
    assert stats["backfilled"] == 2
    assert stats["skipped_bad_date"] == 2

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = {r["fact_id"]: dict(r) for r in con.execute("SELECT * FROM fact_validity")}
    con.close()
    assert set(rows) == {"R1", "R2"}
    for fact_id, date in (("R1", "2026-02-25"), ("R2", "2026-09-13")):
        row = rows[fact_id]
        assert row["valid_from"] == date == row["trans_from"]
        assert row["valid_to"] is None and row["trans_to"] is None
        assert row["t_invalid"] == 0
        assert row["source_rec_id"] == fact_id


# --------------------------------------------------------------------------- #
# 3. Legacy DB (records/records_fts only) degrades gracefully; schema auto-created
# --------------------------------------------------------------------------- #
def test_legacy_db_without_new_tables_degrades_gracefully(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-03-05", "user", "旧库没有任何新表，区间查询应直接过滤 records.created_at"),
            ("R2", "2026-10-05", "assistant", "第二条在下半年，区间查询应当排除"),
        ],
    )
    # Prove the derived tables do not exist yet.
    con = sqlite3.connect(str(db))
    existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "fact_validity" not in existing
    assert "relations" not in existing

    rows = mod05.query_time_range(db, since="2026-01-01", until="2026-06-30")
    assert [r["rec_id"] for r in rows] == ["R1"]

    as_of_rows = mod05.query_as_of(db, "2026-04-01")
    assert [r["rec_id"] for r in as_of_rows] == ["R1"]

    # After the call the schema exists, but the table stays empty (no rebuild).
    con = sqlite3.connect(str(db))
    existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    count = con.execute("SELECT count(*) FROM fact_validity").fetchone()[0]
    con.close()
    assert "fact_validity" in existing
    assert count == 0


# --------------------------------------------------------------------------- #
# 4. AS OF: old fact visible mid-window, replaced fact invisible before its date
# --------------------------------------------------------------------------- #
def test_as_of_returns_old_fact_and_excludes_new(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-01-10", "user", "旧事实：年初的主张"),
            ("R2", "2026-06-01", "user", "新事实：六月推翻旧主张"),
        ],
    )
    mod05.backfill_from_records(db)
    mod05.invalidate_fact(db, "R1", "R2")

    mid = mod05.query_as_of(db, "2026-03-01")
    assert [r["rec_id"] for r in mid] == ["R1"]

    late = mod05.query_as_of(db, "2026-07-01")
    assert [r["rec_id"] for r in late] == ["R2"]

    early = mod05.query_as_of(db, "2026-01-01")
    assert early == []


# --------------------------------------------------------------------------- #
# 5. Invalidation never deletes history; old row closed and linked to replacement
# --------------------------------------------------------------------------- #
def test_invalidation_never_deletes_history(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-01-10", "user", "被取代的旧事实"),
            ("R2", "2026-06-01", "user", "取代旧事实的新事实"),
        ],
    )
    mod05.backfill_from_records(db)
    old = mod05.invalidate_fact(db, "R1", "R2")

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    total = con.execute("SELECT count(*) FROM fact_validity").fetchone()[0]
    row = dict(con.execute("SELECT * FROM fact_validity WHERE fact_id='R1'").fetchone())
    con.close()

    assert total == 2  # history row preserved, not deleted
    assert row["valid_to"] == "2026-06-01"  # = replacement fact's valid_from (Graphiti rule)
    assert row["trans_to"] is not None
    assert row["t_invalid"] == 1
    assert row["superseded_by"] == "R2"
    assert old["superseded_by"] == "R2"


# --------------------------------------------------------------------------- #
# 6. Dual clocks diverge after a late-known fact is recorded
# --------------------------------------------------------------------------- #
def test_transaction_clock_differs_after_invalidation(tmp_path: pathlib.Path) -> None:
    db = _make_db(tmp_path, [("R1", "2026-01-10", "user", "一条迟到才被系统获知的事实")])
    mod05.backfill_from_records(db)

    # Simulate a late-discovered fact: world time T starts in January, but the
    # system only learned it in May (T' differs from T).
    con = sqlite3.connect(str(db))
    con.execute(
        """
        UPDATE fact_validity SET valid_from='2026-01-10', trans_from='2026-05-01'
         WHERE fact_id='R1'
        """
    )
    con.commit()
    con.close()

    valid_view = mod05.query_as_of(db, "2026-03-01", clock="valid")
    assert [r["rec_id"] for r in valid_view] == ["R1"]  # true in the world in March

    transaction_view = mod05.query_as_of(db, "2026-03-01", clock="transaction")
    assert transaction_view == []  # system had not learned it yet in March

    later = mod05.query_as_of(db, "2026-06-01", clock="transaction")
    assert [r["rec_id"] for r in later] == ["R1"]


# --------------------------------------------------------------------------- #
# 7. Range overlap: open intervals included, boundaries inclusive, gaps excluded
# --------------------------------------------------------------------------- #
def test_time_range_overlap_includes_open_interval_and_boundaries(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-03-01", "user", "开放区间事实：三月起一直有效"),
            ("R2", "2026-06-01", "user", "闭合区间事实：六月到八月"),
            ("R3", "2026-10-01", "user", "十月事实，不在春夏区间"),
        ],
    )
    mod05.backfill_from_records(db)
    con = sqlite3.connect(str(db))
    # Close R2's world window explicitly.
    con.execute("UPDATE fact_validity SET valid_to='2026-08-01' WHERE fact_id='R2'")
    con.commit()
    con.close()

    spring_summer = mod05.query_time_range(db, since="2026-03-01", until="2026-08-01")
    assert {r["rec_id"] for r in spring_summer} == {"R1", "R2"}

    # Range filters on the fact's start date: R2 started 2026-06-01, so a range
    # starting 2026-08-01 no longer contains it. AS OF its valid_to date it is
    # excluded too (half-open window [valid_from, valid_to)).
    late_range = mod05.query_time_range(db, since="2026-08-01", until="2026-09-30")
    assert all(r["rec_id"] != "R2" for r in late_range)
    as_of_end = mod05.query_as_of(db, "2026-08-01")
    assert all(r["rec_id"] != "R2" for r in as_of_end)

    autumn = mod05.query_time_range(db, since="2026-09-01", until="2026-09-30")
    assert autumn == []


# --------------------------------------------------------------------------- #
# 8. Corrupted / empty created_at must not crash backfill or queries
# --------------------------------------------------------------------------- #
def test_corrupted_created_at_does_not_crash(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-09-19", "user", "正常日期记录"),
            ("R2", "2026/09/19", "user", "斜杠格式坏日期"),
            ("R3", "??", "user", "问号坏日期"),
            ("R4", "unknown", "user", "未知日期"),
        ],
    )
    stats = mod05.backfill_from_records(db)
    assert stats["backfilled"] == 1
    assert stats["skipped_bad_date"] == 3

    rows = mod05.query_time_range(db, since="2026-01-01", until="2026-12-31")
    assert [r["rec_id"] for r in rows] == ["R1"]
    as_of = mod05.query_as_of(db, "2026-12-31")
    assert [r["rec_id"] for r in as_of] == ["R1"]


# --------------------------------------------------------------------------- #
# 9. Empty database: all roads return empty, no fake results
# --------------------------------------------------------------------------- #
def test_empty_result_on_empty_db(tmp_path: pathlib.Path) -> None:
    db = _make_db(tmp_path, [])
    assert mod05.query_time_range(db) == []
    assert mod05.query_as_of(db, "2026-01-01") == []
    assert mod06.graph_neighbors(db, "Python") == []
    report = mod07.run_recall(db, keyword="验收")
    assert report["counts"] == {"temporal": 0, "graph": 0, "keyword": 0}


# --------------------------------------------------------------------------- #
# 10. Graph extraction: negation clauses must not produce edges
# --------------------------------------------------------------------------- #
def test_graph_extraction_respects_negation_guardrail(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-09-01", "user", "先不要学习 Python，我自己先把基础概念看完"),
            ("R2", "2026-09-02", "user", "我学习 Python 编程，打算先把语法过一遍"),
        ],
    )
    stats = mod06.build_graph(db, lexicon=["Python"], rebuild=True)
    assert stats["edges"] >= 1

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    edges = [dict(r) for r in con.execute("SELECT * FROM relations WHERE relation='LEARNS'")]
    con.close()

    assert len(edges) == 1
    assert edges[0]["rec_id"] == "R2"
    assert edges[0]["object"] == "Python"
    assert all(e["rec_id"] != "R1" for e in edges)


# --------------------------------------------------------------------------- #
# 11. One-hop neighbors carry provenance; two-hop BFS reaches the second layer
# --------------------------------------------------------------------------- #
def test_graph_neighbors_one_hop_provenance_and_two_hop(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-09-01", "user", "我学习 Python 编程基础"),
            ("R2", "2026-09-02", "user", "Python 和 FastAPI 经常搭配在一起使用"),
            ("R3", "2026-09-03", "user", "FastAPI 和 Uvicorn 一起部署上线"),
        ],
    )
    mod06.build_graph(db, lexicon=["Python", "FastAPI", "Uvicorn"], rebuild=True)

    one_hop = mod06.graph_neighbors(db, "Python", hops=1)
    assert one_hop, "one-hop neighborhood must not be empty"
    for edge in one_hop:
        # Every edge must trace back to a real record (provenance).
        assert edge["rec_id"].startswith("R")
        con = sqlite3.connect(str(db))
        assert con.execute("SELECT count(*) FROM records WHERE rec_id=?", (edge["rec_id"],)).fetchone()[0] == 1
        con.close()

    two_hop = mod06.graph_neighbors(db, "Python", hops=2)
    two_hop_objects = {e["object"] for e in two_hop} | {e["subject"] for e in two_hop}
    assert "Uvicorn" in two_hop_objects  # second layer reached via FastAPI
    one_hop_objects = {e["object"] for e in one_hop} | {e["subject"] for e in one_hop}
    assert "FastAPI" in one_hop_objects


def test_third_person_statement_is_not_attributed_to_self(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [("R1", "2026-09-01", "user", "Python 使用 FastAPI 部署服务，这是第三方的事实描述")],
    )
    mod06.build_graph(db, lexicon=["Python", "FastAPI"], rebuild=True)
    con = sqlite3.connect(str(db))
    typed = con.execute(
        "SELECT count(*) FROM relations WHERE relation IN "
        "('LEARNS','USES','WORKS_AT','LIVES_IN','LIKES','RESPONSIBLE_FOR','PREPARES_FOR')"
    ).fetchone()[0]
    con.close()
    assert typed == 0


# --------------------------------------------------------------------------- #
# 12. Graph edges honor the valid-time window under AS OF
# --------------------------------------------------------------------------- #
def test_as_of_filter_on_graph_edges(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [("R1", "2026-09-01", "user", "我学习 Python 编程基础")],
    )
    mod06.build_graph(db, lexicon=["Python"], rebuild=True)

    early = mod06.graph_neighbors(db, "Python", as_of="2026-01-01")
    assert early == []

    later = mod06.graph_neighbors(db, "Python", as_of="2026-09-10")
    assert len(later) == 1
    assert later[0]["valid_from"] == "2026-09-01"


# --------------------------------------------------------------------------- #
# 13. FTS keyword can be combined with the temporal range filter
# --------------------------------------------------------------------------- #
def test_keyword_combined_with_temporal_filter(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-03-10", "user", "这次先把验收标准定清楚再开工"),
            ("R2", "2026-10-20", "user", "十月复盘时又提到验收标准要写进档案"),
            ("R3", "2026-10-21", "assistant", "这条不含关键词，只用于对照"),
        ],
    )
    mod05.backfill_from_records(db)

    spring = mod05.query_time_range(db, since="2026-03-01", until="2026-03-31", keyword="验收")
    assert [r["rec_id"] for r in spring] == ["R1"]

    autumn = mod05.query_time_range(db, since="2026-10-01", until="2026-10-31", keyword="验收")
    assert [r["rec_id"] for r in autumn] == ["R2"]

    report = mod07.run_recall(db, since="2026-10-01", until="2026-10-31", keyword="验收")
    assert report["counts"]["keyword"] >= 1
    assert {r["rec_id"] for r in report["temporal"]} == {"R2"}


# --------------------------------------------------------------------------- #
# 14. #10 integration: event_date drives valid_from, created_at drives trans_from
# --------------------------------------------------------------------------- #
def test_backfill_uses_event_date_for_valid_time(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [("R1", "2026-11-20", "user", "我去年秋天开始学习 Python")],
        event_dates={"R1": "2025-10-01"},
    )
    mod05.backfill_from_records(db)
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    row = dict(con.execute("SELECT * FROM fact_validity WHERE fact_id='R1'").fetchone())
    con.close()
    assert row["valid_from"] == "2025-10-01"
    assert row["trans_from"] == "2026-11-20"
    assert row["valid_from"] != row["trans_from"]


def test_graph_build_uses_event_date_for_edges(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [("R1", "2026-11-20", "user", "我学习 Python 编程基础")],
        event_dates={"R1": "2025-10-01"},
    )
    mod06.build_graph(db, lexicon=["Python"], rebuild=True)
    con = sqlite3.connect(str(db))
    row = con.execute("SELECT valid_from, trans_from FROM relations WHERE rec_id='R1'").fetchone()
    con.close()
    assert row[0] == "2025-10-01"
    assert row[1] == "2026-11-20"


def test_unknown_event_time_is_not_faked_as_mention_date(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [
            ("R1", "2026-11-20", "user", "我去年秋天开始学习 Python"),
            ("R2", "2026-11-21", "user", "我很早以前做过一个项目，具体日期记不清"),
        ],
        event_dates={"R1": "2025-10-01", "R2": "[记忆，待核]"},
    )
    stats = mod05.backfill_from_records(db)
    assert stats["unknown_event"] == 1
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = {r["fact_id"]: dict(r) for r in con.execute("SELECT * FROM fact_validity")}
    con.close()
    assert rows["R1"]["valid_from"] == "2025-10-01"
    assert rows["R2"]["valid_from"] == ""
    assert rows["R2"]["trans_from"] == "2026-11-21"

    valid_view = mod05.query_as_of(db, "2026-01-01", clock="valid")
    assert [r["rec_id"] for r in valid_view] == ["R1"]
    transaction_view = mod05.query_as_of(db, "2026-11-22", clock="transaction")
    assert {r["rec_id"] for r in transaction_view} == {"R1", "R2"}


# --------------------------------------------------------------------------- #
# 15. No time / graph filter must not fabricate a full-table hit
# --------------------------------------------------------------------------- #
def test_run_recall_without_filters_returns_no_temporal_or_graph_rows(tmp_path: pathlib.Path) -> None:
    db = _make_db(
        tmp_path,
        [("R1", "2026-09-01", "user", "我学习 Python 编程基础")],
    )
    mod06.build_graph(db, lexicon=["Python"], rebuild=True)
    report = mod07.run_recall(db, keyword="Python")
    assert report["temporal"] == []
    assert report["graph"] == []
    assert report["counts"]["temporal"] == 0
    assert report["counts"]["graph"] == 0
    assert report["counts"]["keyword"] >= 1
