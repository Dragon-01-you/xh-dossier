#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 3.2: Four-way matching pipeline (Keyword + Vector + Mean-Centered Clustering + Guardrailed Pattern Magnet)."""

from __future__ import annotations

import argparse
import importlib.util
import math
import pathlib
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from importlib import import_module
from typing import Iterable

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_mod01 = import_module("01_clean_and_index")
search_keyword = _mod01.search_keyword

NEGATION_MARKERS = ("先不要", "不要", "先别", "别直接", "禁止", "绝不", "未曾", "还没")
SUBJECT_AI_MISS = ("你没理解", "你还是没理解", "ai老跑偏", "ai没听懂", "完全没理解我")
SUBJECT_USER_MISS = ("我没听懂", "我没看懂", "我不懂你讲", "没明白你说的")


def chunk_text(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """Split long conversations into overlapping chunks so tail details are never truncated."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    step = max(1, size - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        chunks.append(cleaned[start : start + size])
        if start + size >= len(cleaned):
            break
        start += step
    return chunks


def _char_ngrams(text: str) -> Counter[str]:
    norm = re.sub(r"\s+", "", text.lower())
    if not norm:
        return Counter()
    grams = list(norm)
    grams.extend(norm[i : i + 2] for i in range(len(norm) - 1))
    return Counter(grams)


def _l2_normalize_dict(vec: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm <= 1e-12:
        return {}
    return {k: v / norm for k, v in vec.items()}


def cosine_sim(v1: dict[str, float], v2: dict[str, float]) -> float:
    """Compute sparse cosine similarity between two normalized feature dicts."""
    if not v1 or not v2:
        return 0.0
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    return sum(val * v2.get(k, 0.0) for k, val in v1.items())


def build_tfidf_vectors(texts: list[str], extra_queries: list[str] | None = None) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Build L2-normalized chunk-averaged TF-IDF character n-gram vectors and IDF map."""
    doc_grams = [_char_ngrams(" ".join(chunk_text(t))) for t in texts]
    all_df: Counter[str] = Counter()
    for cg in doc_grams:
        for k in cg:
            all_df[k] += 1
    n_docs = max(1, len(texts))
    idf = {k: math.log((n_docs + 1) / (df + 1)) + 1.0 for k, df in all_df.items()}

    if extra_queries:
        for q in extra_queries:
            for k in _char_ngrams(q):
                idf.setdefault(k, math.log(n_docs + 1) + 1.0)

    rec_vectors: list[dict[str, float]] = []
    for text in texts:
        chunks = chunk_text(text)
        if not chunks:
            rec_vectors.append({})
            continue
        merged: dict[str, float] = defaultdict(float)
        for ch in chunks:
            ch_grams = _char_ngrams(ch)
            ch_vec = _l2_normalize_dict({k: tf * idf.get(k, 1.0) for k, tf in ch_grams.items()})
            for k, val in ch_vec.items():
                merged[k] += val / len(chunks)
        rec_vectors.append(_l2_normalize_dict(dict(merged)))
    return rec_vectors, idf


def vectorize_query(query: str, idf: dict[str, float]) -> dict[str, float]:
    """Project query into the exact un-centered rec_raw vector space."""
    grams = _char_ngrams(query)
    return _l2_normalize_dict({k: tf * idf.get(k, 1.0) for k, tf in grams.items()})


def mean_center_and_normalize(vectors: list[dict[str, float]]) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Subtract dataset centroid mu to remove anisotropy before density clustering (keeps significant sparse entries)."""
    if not vectors:
        return [], {}
    n = len(vectors)
    mu: dict[str, float] = defaultdict(float)
    for vec in vectors:
        for k, v in vec.items():
            mu[k] += v / n
    # Only propagate meaningful centroid weights to avoid O(N*V) dense noise on large corpora
    mu_sig = {k: v for k, v in mu.items() if abs(v) > 1e-4}
    mu_norm_sq = sum(v * v for v in mu_sig.values())

    centered: list[dict[str, float]] = []
    for vec in vectors:
        shifted: dict[str, float] = {}
        # Norm of (v - mu) = sqrt(||v||^2 - 2<v, mu> + ||mu||^2) avoids scanning zero keys for norm
        v_sq = sum(val * val for val in vec.values())
        v_dot_mu = sum(val * mu_sig.get(k, 0.0) for k, val in vec.items())
        denom = math.sqrt(max(0.0, v_sq - 2.0 * v_dot_mu + mu_norm_sq))
        if denom <= 1e-12:
            centered.append({})
            continue
        for k, val in vec.items():
            diff = val - mu_sig.get(k, 0.0)
            if abs(diff) > 1e-5:
                shifted[k] = diff / denom
        for k, mval in mu_sig.items():
            if k not in vec and abs(mval) > 0.01:
                shifted[k] = -mval / denom
        centered.append(shifted)
    return centered, dict(mu)


def cluster_vectors(centered_vectors: list[dict[str, float]], sim_threshold: float = 0.25, min_cluster_size: int = 2) -> list[int]:
    """Greedy cosine density clustering using O(N * nnz) incremental centroid updates."""
    clusters: list[list[int]] = []
    centroid_sums: list[dict[str, float]] = []
    centroids: list[dict[str, float]] = []

    for idx, vec in enumerate(centered_vectors):
        best_c = -1
        best_sim = -1.0
        for c_idx, cent in enumerate(centroids):
            s = cosine_sim(vec, cent)
            if s >= sim_threshold and s > best_sim:
                best_sim = s
                best_c = c_idx
        if best_c >= 0:
            clusters[best_c].append(idx)
            csum = centroid_sums[best_c]
            for k, val in vec.items():
                csum[k] = csum.get(k, 0.0) + val
            centroids[best_c] = _l2_normalize_dict(csum)
        else:
            clusters.append([idx])
            centroid_sums.append(dict(vec))
            centroids.append(vec)

    labels = [-1] * len(centered_vectors)
    next_cid = 0
    for c_members in clusters:
        if len(c_members) >= min_cluster_size:
            for idx in c_members:
                labels[idx] = next_cid
            next_cid += 1
    return labels


def apply_guardrails(content: str, pattern_kind: str) -> tuple[bool, str]:
    """Guard against Subject-Object Inversion and Negation Blindness before pattern backfill."""
    lowered = content.lower()
    if pattern_kind == "ai_misunderstood_user":
        has_user_self = any(tok in lowered for tok in SUBJECT_USER_MISS)
        has_ai_miss = any(tok in lowered for tok in SUBJECT_AI_MISS)
        if has_user_self and not has_ai_miss:
            return False, "filtered:subject_object_inversion(user_did_not_understand)"

    if pattern_kind in {"affirmative_action", "method_principle"}:
        if any(neg in lowered for neg in NEGATION_MARKERS):
            return False, "filtered:negation_marker_present"

    return True, "passed"


DEFAULT_PATTERNS = [
    ("ai_misunderstood_user", "反复纠正AI还是没理解真实意图", ["你还是没理解我", "说了十遍AI记错", "没有听懂什么意思", "没听懂你讲"]),
    ("affirmative_action", "卡在完美主义拖延或没上线交付", ["做完一直没发出去", "卡在改细节没上线", "停在最后10%"]),
    ("method_principle", "先定验收标准再动手", ["开工先定验收标准", "先想清楚问题是什么再写"]),
]


def _encode_with_fastembed(texts: list[str], queries: list[str]) -> tuple[list[dict[str, float]], list[dict[str, float]]] | None:
    if importlib.util.find_spec("fastembed") is None:
        return None
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")
    t_vecs = list(model.embed(texts))
    q_vecs = list(model.embed(queries))
    doc_dicts = [_l2_normalize_dict({str(i): float(v) for i, v in enumerate(arr)}) for arr in t_vecs]
    q_dicts = [_l2_normalize_dict({str(i): float(v) for i, v in enumerate(arr)}) for arr in q_vecs]
    return doc_dicts, q_dicts


def run_four_way_pipeline(
    db_path: pathlib.Path,
    keywords: Iterable[str],
    use_fastembed: bool = False,
    cluster_threshold: float | None = None,
    pattern_threshold: float = 0.16,
) -> dict:
    """Execute all 4 matching ways on records in db_path and return structured evidence for backfill."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("SELECT rec_id, source_file, created_at, role, content FROM records ORDER BY rec_id").fetchall()]
    finally:
        con.close()

    if not rows:
        return {"records": 0, "keyword_hits": {}, "clusters": {}, "pattern_hits": {}}

    texts = [r["content"] for r in rows]
    kw_results = {kw: search_keyword(db_path, kw, limit=15) for kw in keywords}

    flat_seeds = [s for _, _, seeds in DEFAULT_PATTERNS for s in seeds]
    if use_fastembed:
        fe = _encode_with_fastembed(texts, flat_seeds)
        if fe is not None:
            rec_raw, fe_q = fe
            seed_vecs = {s: v for s, v in zip(flat_seeds, fe_q)}
        else:
            rec_raw, idf = build_tfidf_vectors(texts, flat_seeds)
            seed_vecs = {s: vectorize_query(s, idf) for s in flat_seeds}
    else:
        rec_raw, idf = build_tfidf_vectors(texts, flat_seeds)
        seed_vecs = {s: vectorize_query(s, idf) for s in flat_seeds}

    rec_centered, _mu = mean_center_and_normalize(rec_raw)
    eff_cluster_th = (0.02 if len(rows) < 25 else 0.20) if cluster_threshold is None else cluster_threshold
    labels = cluster_vectors(rec_centered, sim_threshold=eff_cluster_th, min_cluster_size=2)
    cluster_map: dict[int, list[dict]] = defaultdict(list)
    for row, cid in zip(rows, labels):
        cluster_map[cid].append(row)

    pattern_hits: dict[str, dict] = {}
    for kind, title, seeds in DEFAULT_PATTERNS:
        passed = []
        filtered = []
        for idx, (row, vec) in enumerate(zip(rows, rec_raw)):
            score = max((cosine_sim(vec, seed_vecs[s]) for s in seeds), default=0.0)
            if score < pattern_threshold:
                continue
            ok, reason = apply_guardrails(row["content"], kind)
            item = {
                "rec_id": row["rec_id"],
                "created_at": row["created_at"],
                "cluster": labels[idx],
                "score": round(score, 4),
                "reason": reason,
                "excerpt": row["content"][:160].replace("\n", " "),
            }
            if ok:
                passed.append(item)
            else:
                filtered.append(item)
        passed.sort(key=lambda x: x["score"], reverse=True)
        sampled = []
        if passed:
            indices = sorted({0, len(passed) // 2, len(passed) - 1})
            sampled = [passed[i] for i in indices]
        clusters_spanned = sorted({item["cluster"] for item in passed})
        pattern_hits[title] = {
            "kind": kind,
            "passed_count": len(passed),
            "filtered_count": len(filtered),
            "clusters_spanned": clusters_spanned,
            "sampled": sampled,
            "filtered": filtered[:5],
        }

    return {
        "records": len(rows),
        "keyword_hits": kw_results,
        "clusters": dict(cluster_map),
        "pattern_hits": pattern_hits,
    }


def render_backfill_markdown(report: dict) -> str:
    """Format 4-way pipeline findings into a human-auditable backfill report."""
    lines = [
        "# 四路匹配与人工抽样回填候选项（backfill_candidates）",
        "",
        f"> 已索引唯一原文条数：`{report['records']}` ｜ 所有项需本人复核带 `[REC-xxxx]` 原文后，才准从 `[待确认]` 转正入卡。",
        "",
        "## 一、Way 1 · 精准关键词直查命中",
        "",
    ]
    for kw, hits in report["keyword_hits"].items():
        lines.append(f"- 关键词 **`{kw}`**：命中 `{len(hits)}` 条")
        for h in hits[:3]:
            lines.append(f"  - `[{h['rec_id']} | {h['created_at']}]` {h['content'][:100].replace(chr(10), ' ')}")

    lines.extend(["", "## 二、Way 3 · 去均值余弦聚类话题簇", ""])
    for cid, items in sorted(report["clusters"].items()):
        tag = "长尾未成簇 (-1)" if cid == -1 else f"话题簇 #{cid}"
        lines.append(f"- **{tag}**（`{len(items)}` 条）：示例 `[{items[0]['rec_id']}]` {items[0]['content'][:75].replace(chr(10), ' ')}")

    lines.extend(["", "## 三、Way 2 & Way 4 · 跨簇语义模式挖掘 + 主宾/否定防误报拦截", ""])
    for title, info in report["pattern_hits"].items():
        span = len(info.get("clusters_spanned", []))
        lines.append(
            f"### 模式：`{title}`（跨越 `{span}` 个簇/长尾 ｜ 通过 `{info['passed_count']}` 条 ｜ 门禁拦截 `{info['filtered_count']}` 条误报）"
        )
        for s in info["sampled"]:
            lines.append(f"- `[待确认]` `[{s['rec_id']} | sim={s['score']} | cluster={s['cluster']}]` {s['excerpt']}")
        for f in info["filtered"]:
            lines.append(f"- ~~[已拦截 · {f['reason']}]~~ `[{f['rec_id']} | sim={f['score']}]` {f['excerpt']}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 4-way matching & false-positive guardrails on unified_index.db.")
    parser.add_argument("--db", required=True, type=pathlib.Path, help="Path to unified_index.db")
    parser.add_argument("--out", required=True, type=pathlib.Path, help="Output markdown report path")
    parser.add_argument("--keywords", nargs="*", default=["记错", "验收", "拖延", "口音"], help="Exact keywords for Way 1")
    parser.add_argument("--use-fastembed", action="store_true", help="Use fastembed BAAI/bge-small-zh-v1.5 if installed")
    args = parser.parse_args()

    # Expected input failures get a plain-language, actionable message; unexpected ones
    # still raise so real bugs keep their traceback for diagnosis.
    try:
        report = run_four_way_pipeline(args.db, args.keywords, use_fastembed=args.use_fastembed)
    except FileNotFoundError:
        print(f"DB_NOT_FOUND: {args.db}")
        print("  这里要填的是上一步生成的 unified_index.db，需要先跑 01_clean_and_index.py。")
        print("  例：python -X utf8 scripts/01_clean_and_index.py --raw raw --db work/unified_index.db")
        return 2

    if report["records"] == 0:
        print(f"EMPTY_DB: {args.db} 里没有任何对话记录，无法做四路匹配。")
        print("  通常是上一步导出目录是空的，先确认 raw/ 里确实有导出的原件。")
        return 2

    md = render_backfill_markdown(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"FOUR_WAY_OK records={report['records']} clusters={len(report['clusters'])} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
