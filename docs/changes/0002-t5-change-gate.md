script: scripts/15_change_gate.py
status: new

## 改前

{"run_id": "t5-before", "step": "15_change_gate", "counter_version": "v1", "input_count": 0, "output_count": 0, "new_count": null, "actor": "main", "exit_code": 0, "seconds": 0.0, "timestamp": "2026-11-27T15:20:00+08:00", "note": "新增脚本，无改前基线"}

## 改后

{"run_id": "t5-after", "step": "15_change_gate", "counter_version": "v1", "input_count": 1, "output_count": 1, "new_count": 1, "actor": "main", "exit_code": 0, "seconds": 0.104, "timestamp": "2026-11-27T15:21:00+08:00", "note": "新增脚本，无改前基线；一次仅文档改动的门禁运行"}

## 差异

- `run_id`: t5-before → t5-after
- `step`: 无变化
- `counter_version`: 无变化
- `input_count`: 0 → 1
- `output_count`: 0 → 1
- `new_count`: null → 1
- `actor`: 无变化
- `exit_code`: 无变化
- `seconds`: 0.0 → 0.104
- `timestamp`: 2026-11-27T15:20:00+08:00 → 2026-11-27T15:21:00+08:00
- `note`: 新增脚本，无改前基线 → 新增脚本，无改前基线；一次仅文档改动的门禁运行

新增脚本，无改前基线：这个 PR 第一次引入 `15_change_gate.py`，改前没有可执行版本，所以改前行输入输出均为 0，`new_count` 为 null。
