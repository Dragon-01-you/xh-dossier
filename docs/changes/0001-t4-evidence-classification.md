script: scripts/05b_l2_theme.py
status: modified

## 改前

{"run_id": "t4-before-real", "step": "05b_l2_theme", "counter_version": "v1", "input_count": 346, "output_count": 6, "new_count": 6, "actor": "main", "exit_code": 0, "seconds": 0.671, "timestamp": "2026-11-27T15:10:00+08:00", "note": "改前：来源数=命中的文件数；729 条总记录中的 346 条本人记录"}

## 改后

{"run_id": "t4-after-real", "step": "05b_l2_theme", "counter_version": "v1", "input_count": 346, "output_count": 4, "new_count": 4, "actor": "main", "exit_code": 0, "seconds": 0.703, "timestamp": "2026-11-27T15:12:00+08:00", "note": "改后：证据三分类，personal_docs<2 打回；plain_language 与 real_project_test 被打回"}

## 差异

- `run_id`: t4-before-real → t4-after-real
- `step`: 无变化
- `counter_version`: 无变化
- `input_count`: 无变化
- `output_count`: 6 → 4
- `new_count`: 6 → 4
- `actor`: 无变化
- `exit_code`: 无变化
- `seconds`: 0.671 → 0.703
- `timestamp`: 2026-11-27T15:10:00+08:00 → 2026-11-27T15:12:00+08:00
- `note`: 改前：来源数=命中的文件数；729 条总记录中的 346 条本人记录 → 改后：证据三分类，personal_docs<2 打回；plain_language 与 real_project_test 被打回

## 依据

真实库 `/home/user/xh-overnight-20261125/work/real/unified_index.db`（729 条，本人 346 条），
两次都用同一套 `work/real/kit` 与 `backfill_candidates.md`。改前候选 6 条、改后 4 条；
被打回的两条主题在报告“打回候选”表里可见（`plain_language` personal=1/hits=6）。
