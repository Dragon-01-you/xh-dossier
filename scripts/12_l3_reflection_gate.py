#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.6 · Layer 3 Reflection Minimum Programmatic Gate (Issue #132 / Spec #128).

Thin, zero-dependency Python hard-gate contract for L3 Observations (distilled
across multiple L1/L2 facts, inspired by Hindsight `Raw Facts -> Observations ->
Mental Models` and Basic Memory offline reflection).

This script does NOT auto-run in background and NEVER writes to the 6-file kit
without explicit personal sign-off. It enforces 4 objective, mechanical gates
(no subjective percentage thresholds):

1. ``G1_MULTI_EVIDENCE``: >= 2 verified user records from >= 2 distinct calendar
   dates AND >= 2 distinct sessions (``source_file``), each with a real ``rec_id``
   and exact matching ``quote`` in SQLite.
2. ``G2_L2_PARAPHRASE``: rejects observations that merely copy or lightly reword
   a single cited record or L2 candidate excerpt.
3. ``G3_COUNTEREXAMPLE_AND_EVOLUTION``: requires explicit ``counterexamples`` slot
   (verified against SQLite whenever non-empty) and non-empty ``evolution`` note.
4. ``G4_HUMAN_SIGNOFF_REQUIRED``: blocks any promotion into official kit files
   (especially ``02-核心判断准则.md`` / ``04-正反例避坑账.md``) unless signed by
   the user (``status == 'signed'``, ``signed_by``, ``signed_at``, ``confirm=True``).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
import sys
import unicodedata
from typing import Any, Iterable

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from sqlite_compat import connect_db

PROTECTED_TARGETS = frozenset({
    "AGENTS.md",
    "00-总入口索引.md",
    "01-身份与当前主线.md",
    "02-核心判断准则.md",
    "03-硬规则与表达黑话.md",
    "04-正反例避坑账.md",
    "04-反面案例清单.md",
})

_PUNCT_RE = re.compile(
    r"[\s，。！？、；：“”‘’「」『』（）()\[\]【】《》,.!?;:\-_—…/\\|｜·•`~*#\"']+"
)
_ISO_DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}")


def _norm_quote(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def _fold_text(text: str) -> str:
    return _PUNCT_RE.sub("", unicodedata.normalize("NFKC", text or "")).lower()


def _bigrams(text: str) -> set[str]:
    f = _fold_text(text)
    if len(f) < 2:
        return set()
    return {f[i:i + 2] for i in range(len(f) - 1)}


def _is_paraphrase_of_single(statement: str, source_text: str) -> bool:
    """Deterministic anti-paraphrase check against a single record/excerpt."""
    f_stmt = _fold_text(statement)
    f_src = _fold_text(source_text)
    if not f_stmt or not f_src:
        return False
    if f_stmt in f_src or (len(f_src) >= 12 and f_src in f_stmt and len(f_src) / max(len(f_stmt), 1) >= 0.7):
        return True
    bg_stmt = _bigrams(statement)
    bg_src = _bigrams(source_text)
    if not bg_stmt or not bg_src:
        return False
    containment = len(bg_stmt & bg_src) / len(bg_stmt)
    return containment >= 0.65


def _load_records_map(db_path: pathlib.Path) -> dict[str, dict[str, str]]:
    if not db_path.is_file():
        raise FileNotFoundError(f"DB_NOT_FOUND: {db_path}")
    con = connect_db(db_path)
    con.row_factory = sqlite3.Row
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(records)").fetchall()]
        has_event = "event_date" in cols
        sql = (
            "SELECT rec_id, source_file, created_at, event_date, role, content FROM records"
            if has_event
            else "SELECT rec_id, source_file, created_at, role, content FROM records"
        )
        return {r["rec_id"]: dict(r) for r in con.execute(sql).fetchall()}
    finally:
        con.close()


def _record_date(rec: dict[str, str]) -> str:
    ev = str(rec.get("event_date") or "").strip()
    if _ISO_DATE_RE.match(ev):
        return ev[:10]
    cr = str(rec.get("created_at") or "").strip()
    if _ISO_DATE_RE.match(cr):
        return cr[:10]
    return ""


def _verify_evidence_item(item: Any, rec_map: dict[str, dict[str, str]]) -> tuple[bool, str, dict[str, str] | None]:
    if not isinstance(item, dict):
        return False, "evidence_item_not_object", None
    rec_id = str(item.get("rec_id") or "").strip()
    quote = str(item.get("quote") or "").strip()
    rec = rec_map.get(rec_id)
    if rec is None:
        return False, f"rec_id_not_found:{rec_id}", None
    if str(rec.get("role") or "").strip().lower() != "user":
        return False, f"non_user_record:{rec_id}", None
    nq = _norm_quote(quote)
    nc = _norm_quote(str(rec.get("content") or ""))
    if len(nq) < 4 or nq not in nc:
        return False, f"quote_mismatch:{rec_id}", None
    return True, "", rec


def validate_observation(
    db_path: pathlib.Path,
    observation: dict[str, Any],
    *,
    l2_excerpts: Iterable[str] = (),
) -> dict[str, Any]:
    """Run mechanical Gates 1-3 on a single L3 Observation candidate.

    Returns a structured verdict dict; passing Gates 1-3 only qualifies the
    candidate for human review (never auto-promotes into the 6-file kit).
    """
    rec_map = _load_records_map(db_path)
    obs_id = str(observation.get("observation_id") or "OBS-UNKNOWN")
    statement = str(observation.get("statement") or "").strip()
    evidence = observation.get("evidence")
    failed_gates: list[str] = []
    details: list[str] = []

    # --- Gate 1: >=2 verified user records across >=2 dates and >=2 sessions ---
    verified_recs: list[dict[str, str]] = []
    verified_quotes: list[str] = []
    if not isinstance(evidence, list) or len(evidence) < 2:
        failed_gates.append("G1_MULTI_EVIDENCE")
        details.append("证据不足 2 条（每条反思洞察至少需要 2 条不同日期且不同会话的真实用户原文）。")
    else:
        ev_errors: list[str] = []
        seen_rec_ids: set[str] = set()
        for item in evidence:
            ok, err, rec = _verify_evidence_item(item, rec_map)
            if not ok or rec is None:
                ev_errors.append(err)
                continue
            if rec["rec_id"] in seen_rec_ids:
                continue
            seen_rec_ids.add(rec["rec_id"])
            verified_recs.append(rec)
            verified_quotes.append(str(item.get("quote") or ""))
        distinct_dates = {d for r in verified_recs if (d := _record_date(r))}
        distinct_sessions = {str(r.get("source_file") or "").strip() for r in verified_recs if str(r.get("source_file") or "").strip()}
        if ev_errors:
            failed_gates.append("G1_MULTI_EVIDENCE")
            details.append("证据验真失败：" + "; ".join(ev_errors))
        elif len(verified_recs) < 2 or len(distinct_dates) < 2 or len(distinct_sessions) < 2:
            failed_gates.append("G1_MULTI_EVIDENCE")
            details.append(
                f"跨度不足：已验真 {len(verified_recs)} 条、覆盖 {len(distinct_dates)} 个不同日期、"
                f"{len(distinct_sessions)} 个不同会话（硬门禁要求均 ≥2）。"
            )

    # --- Gate 2: anti-L2 single-record paraphrase ---
    if len(_fold_text(statement)) < 12:
        failed_gates.append("G2_L2_PARAPHRASE")
        details.append("洞察表述过短（少于 12 个有效字），不能作为跨事实反思。")
    else:
        compare_pool = (
            [str(r.get("content") or "") for r in verified_recs]
            + verified_quotes
            + [str(x) for x in l2_excerpts if x]
        )
        for src in compare_pool:
            if _is_paraphrase_of_single(statement, src):
                failed_gates.append("G2_L2_PARAPHRASE")
                details.append("洞察表述与单条引用原话/L2 候选字面重合过高，判定为复述 L2 而非跨事实归纳。")
                break

    # --- Gate 3: explicit counterexamples slot + evolution history ---
    has_ce_field = "counterexamples" in observation and isinstance(observation.get("counterexamples"), list)
    evolution = str(observation.get("evolution") or "").strip()
    ce_errors: list[str] = []
    if has_ce_field:
        for ce in observation["counterexamples"]:
            ok, err, _rec = _verify_evidence_item(ce, rec_map)
            if not ok:
                ce_errors.append(err)
    if (not has_ce_field) or (not evolution) or ce_errors:
        failed_gates.append("G3_COUNTEREXAMPLE_AND_EVOLUTION")
        if not has_ce_field:
            details.append("缺少显式 counterexamples 字段（无反例也必须显式写 []）。")
        if not evolution:
            details.append("缺少 evolution 演变历史说明。")
        if ce_errors:
            details.append("反例证据验真失败：" + "; ".join(ce_errors))

    passed = not failed_gates
    return {
        "observation_id": obs_id,
        "passed": passed,
        "failed_gates": list(dict.fromkeys(failed_gates)),
        "details": details,
        "verified_evidence_count": len(verified_recs),
        "ready_for_human_review": passed,
        "promotable": False,  # Gate 4 always requires explicit human sign-off
    }


def check_promotion_gate(
    observation: dict[str, Any],
    *,
    target_profile: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Gate 4: Mechanical sign-off gate before any write to the 6-file kit."""
    failed: list[str] = []
    reasons: list[str] = []
    target_name = pathlib.PurePosixPath(target_profile.replace("\\", "/")).name
    if target_name not in PROTECTED_TARGETS:
        failed.append("G4_TARGET_NOT_WHITELISTED")
        reasons.append(f"目标文件不在 6 份核心档案白名单内：{target_profile}")
    if target_name == "AGENTS.md":
        failed.append("G4_AGENTS_READ_ONLY")
        reasons.append("AGENTS.md 为合作协议硬边界，禁止由 L3 自动写入。")

    status = str(observation.get("status") or "pending").strip().lower()
    signed_by = str(observation.get("signed_by") or "").strip()
    signed_at = str(observation.get("signed_at") or "").strip()
    if status != "signed" or not signed_by or not _ISO_DATE_RE.match(signed_at) or not confirm:
        failed.append("G4_HUMAN_SIGNOFF_REQUIRED")
        reasons.append(
            "缺少本人明确签字（需 status=signed、signed_by、ISO signed_at 且显式 confirm=True），禁止写入正式 6 份档案。"
        )
    return {
        "allowed": not failed,
        "target_profile": target_name,
        "failed_gates": list(dict.fromkeys(failed)),
        "reasons": reasons,
    }


def validate_observations_file(
    db_path: pathlib.Path,
    observations_jsonl: pathlib.Path,
    *,
    l2_excerpts: Iterable[str] = (),
) -> dict[str, Any]:
    if not observations_jsonl.is_file():
        raise FileNotFoundError(f"OBSERVATIONS_NOT_FOUND: {observations_jsonl}")
    results: list[dict[str, Any]] = []
    for idx, line in enumerate(observations_jsonl.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obs = json.loads(line)
        except json.JSONDecodeError:
            results.append({
                "observation_id": f"LINE-{idx}",
                "passed": False,
                "failed_gates": ["INVALID_JSON"],
                "details": ["JSON 解析失败"],
                "ready_for_human_review": False,
                "promotable": False,
            })
            continue
        results.append(validate_observation(db_path, obs, l2_excerpts=l2_excerpts))
    passed_n = sum(1 for r in results if r["passed"])
    return {
        "total": len(results),
        "passed": passed_n,
        "rejected": len(results) - passed_n,
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Layer-3 reflection minimum programmatic gate validator.")
    ap.add_argument("--db", required=True, type=pathlib.Path, help="Cold SQLite records database")
    ap.add_argument("--observations", required=True, type=pathlib.Path, help="JSONL file of L3 observation candidates")
    ap.add_argument("--json", action="store_true", help="Print full JSON report")
    args = ap.parse_args()
    try:
        report = validate_observations_file(args.db, args.observations)
    except FileNotFoundError as exc:
        print(f"L3_GATE_ERROR: {exc}")
        return 2
    print(f"L3_GATE_OK total={report['total']} passed={report['passed']} rejected={report['rejected']}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["rejected"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
