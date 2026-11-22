# Event time vs mention time (Issue #10)

> 目标：用户说“大一那会我做过 X”时，系统不能把 X 记成“今天发生”。
> `created_at` 是你说这句话的日期；`event_date` 是这件事真正发生的日期。

## Schema

`records` 新增两列：

| 列 | 含义 | 例 |
|---|---|---|
| `created_at` | 提到/说到的时间（T'，transaction time） | `2026-11-22` |
| `event_date` | 事件实际发生时间（T，valid time），或 `[记忆，待核]` | `2025-09-20` / `[记忆，待核]` |
| `date_kind` | 判定类型 | `stated` / `retrospective` / `retrospective_month` / `unknown` |

- `stated`：这句话在说当前/明确日期发生的事，`event_date` 为明确日期或 `created_at`。
- `retrospective`：有回忆标记（如“大一那会”“上周”“以前”），但没找到可核对的绝对日期，`event_date = [记忆，待核]`。
- `retrospective_month`：只有月级锚点（如“2025-09”），不伪造具体日。
- `unknown`：这句话没有提出“某事何时发生”的事件时间主张（例如“我觉得你可以看一下这份文档”“现在的目录里有这些资产”），`event_date = ""`；assistant 的 `Thought Process` 同样为 `""`，不参与个人事件时间判定。

## 判定规则

1. 绝对日期必须是配对分隔符：`2025-09-20`、`2025/09/20`、`2025年9月20日`；`2025-123` 版本号不切成日期。
2. 真日历校验：`2025-02-30` 不存在的日期不会写入，落 `[记忆，待核]`。
3. 月级精度保留 `2025-09`，不补成 `2025-09-01`。
4. “记得帮我…”是祈使句，不算回忆；“记得 2025-09-20…”才算。
5. 同一句里出现“今天/刚才/这周”等现在标记，优先判定为 `stated`；单独的“现在/目前”是状态词，只有在带“了/终于/已经/开始”等完成线索时才算现在事件。
6. 没有事件时间主张的普通句子（工作指令、状态描述、现在的目录等）落 `unknown`，不复制 `created_at`。
7. 只对 `role=user` 做事件时间判定；assistant 的思考过程不进个人事件账，`event_date` 留空。

## 旧库迁移

`01_clean_and_index.py` 每次从 `raw/` 重建 DB。旧库没有 `event_date/date_kind`，重跑 01 即可得到新 schema；不要把旧库当成已迁移。

## 验收

```bash
py -3.12 scripts/01_clean_and_index.py --raw <raw> --db <db> --query 大一
```

期望：`INDEX_OK`，查询行显示 `said=... | event=... | retrospective`；`event_date` 为 `[记忆，待核]` 或可核对日期，不是简单复制 `created_at`。
