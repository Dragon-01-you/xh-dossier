# ADR-0001: 6-File Onboarding Kit (`AGENTS.md` + `00~04`) and 4-Way Matching Pipeline

- **Status**: Accepted
- **Date**: 2026-11-21

## Context

When migrating across dozens of web and local AI tools, users commonly face two traps:
1. Confusing whether the final personal kit consists of 5 or 6 files (`AGENTS.md` vs the 5 numbered personal core files `00~04`).
2. Dumping raw exported logs straight into an LLM for "one-shot summarization", which erases voice tone, introduces hallucinated personas, and falls into vector retrieval traps (anisotropy, subject-object inversion, negation blindness).

## Decision

1. **Standardize on the 6-file kit (`1 + 5` explicit split)**:
   - `AGENTS.md`: collaboration protocol & safety guardrails for the Agent.
   - `00-总入口索引.md` ~ `04-正反例避坑账.md`: the 5 personal memory files distilled from interview + evidence backfill, where `02-核心判断准则.md` holds highest leverage.
   Both counts ("5 personal files" vs "6 total files including `AGENTS.md`") are explained explicitly so users of either web prompts (`AGENTS.md` pasted into system instructions) or local Agent CLI tools (`AGENTS.md` auto-loaded from repo/root) stay aligned.
2. **Use a 4-way deterministic + semantic matching pipeline before human backfill**:
   - Step 1 (`01_clean_and_index.py`): clean noise, MD5 deduplicate, build read-only SQLite `FTS5` trigram cold index (`< 3` chars fallback to `LIKE`).
   - Step 2 (`02_four_way_match.py`): combine (1) keyword exact search, (2) chunked vector retrieval (`size=500, overlap=80`), (3) mean-centered cosine clustering (`L2(v - mu)`), and (4) cross-cluster pattern mining guarded against Subject-Object Inversion and Negation Blindness, outputting traceable `[REC:id]` evidence for user backfill (`[待确认]` until user approves).

## Consequences

- Zero LLM dependency required to index, cluster, filter false positives, and audit the onboarding kit in CI.
- Optional `fastembed` (`BAAI/bge-small-zh-v1.5`) integrates seamlessly via `--use-fastembed` when dense Chinese semantic vectors are desired offline, while stdlib TF-IDF char n-gram vectors make testing, demos, and GitHub Actions fast and reproducible.
