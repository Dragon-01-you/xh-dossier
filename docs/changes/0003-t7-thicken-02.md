script: scripts/14_thicken_02.py
status: new

新增脚本，无改前基线：改前一行由同一份真实 kit 的 `--dry-run` 测得（只读，不写文件），
改后一行由正式写入测得。两次输入的 evidence 行数相同、口径版本相同，可以直接对比。

## 改前

{"run_id": "t7-before-real", "step": "14_thicken_02", "counter_version": "v1", "input_count": 109, "output_count": 0, "new_count": 0, "actor": "main", "exit_code": 0, "seconds": 0.137, "timestamp": "2026-11-28T01:22:00+08:00", "note": "改前：02 有据判断 0 条（只有机器归纳句）；01 当前主线候选 3 条"}

## 改后

{"run_id": "t7-after-real", "step": "14_thicken_02", "counter_version": "v1", "input_count": 109, "output_count": 5, "new_count": 5, "actor": "main", "exit_code": 0, "seconds": 0.135, "timestamp": "2026-11-28T01:22:30+08:00", "note": "改后：02 有据判断 5 条、每条带原文与行号；01 当前主线候选 1 条，另 2 条逐字移入历史区；03/04 sha256 不变"}

## 差异

- `run_id`: t7-before-real → t7-after-real
- `step`: 无变化
- `counter_version`: 无变化
- `input_count`: 无变化
- `output_count`: 0 → 5
- `new_count`: 0 → 5
- `actor`: 无变化
- `exit_code`: 无变化
- `seconds`: 0.137 → 0.135
- `timestamp`: 2026-11-28T01:22:00+08:00 → 2026-11-28T01:22:30+08:00
- `note`: 改前：02 有据判断 0 条（只有机器归纳句）；01 当前主线候选 3 条 → 改后：02 有据判断 5 条、每条带原文与行号；01 当前主线候选 1 条，另 2 条逐字移入历史区；03/04 sha256 不变

## 依据

真实档案目录 `work/real/kit`（729 条记录的库，kit 证据摘要 109 行），脚本只读
`_evidence/chat-lines.md`，不碰 raw、不碰库。同一个 kit 跑两次：

| 口径 | 改前 | 改后 |
|---|---|---|
| 02 有据判断（`- **候选` + 原文 + 出处）| 0 条 | 5 条 |
| 01 当前主线候选 | 3 条 | 1 条（另 2 条逐字进 §六 历史区）|
| 打分卡 coverage | 0.83（缺 principle）| 1.00 |
| 打分卡 answerable_questions | 0.67（判断准则答不出）| 1.00 |
| 打分卡 citation_accuracy | 1.00 | 1.00（24/24 可追溯）|
| 打分卡 mainline_unique | 0.00 | 1.00 |
| 03 / 04 sha256 | — | 与改前逐字节相同 |

第二次运行返回 `NOOP` 且不写任何文件，保证可重复跑。
