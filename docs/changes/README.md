# 改动台账（docs/changes）

改 `scripts/*.py` 的 PR，必须在这里带一条记录；CI 的 `Change gate` 会挡住没有记录的改动。

每条记录只管一个脚本，格式：

````markdown
script: scripts/05b_l2_theme.py
status: modified        # modified = 改已有脚本；new = 新增脚本

## 改前

{"run_id": "...", "step": "05b_l2_theme", "counter_version": "v1", "input_count": 346, "output_count": 6, "new_count": 6, "actor": "main", "exit_code": 0, "seconds": 0.671, "timestamp": "2026-11-27T...", "note": "..."}

## 改后

{"run_id": "...", "step": "05b_l2_theme", "counter_version": "v1", "input_count": 346, "output_count": 4, "new_count": 4, "actor": "main", "exit_code": 0, "seconds": 0.703, "timestamp": "2026-11-27T...", "note": "..."}

## 差异

- `run_id`: r-before → r-after
- `step`: 无变化
- `counter_version`: 无变化
- `input_count`: 无变化
- `output_count`: 6 → 4
- `new_count`: 6 → 4
- `actor`: 无变化
- `exit_code`: 无变化
- `seconds`: 0.671 → 0.703
- `timestamp`: 改前 → 改后
- `note`: 改前 → 改后
````

规则（脚本会逐条检查）：

1. 两行台账都是 11 列齐全的 JSON，`step` 与 `counter_version` 必须一致；跨口径不可比。
2. `## 差异` 必须覆盖全部 11 列。
3. 值没变的列，必须显式写“无变化”；留空视为不通过。
4. 值变了的列，必须同时写出改前和改后的值。
5. 新增脚本（`status: new`）要在记录里写明“新增脚本，无改前基线”。
6. 两行完全一样且不是新增脚本 → 视为“没有任何可核对的变化”，不通过。
