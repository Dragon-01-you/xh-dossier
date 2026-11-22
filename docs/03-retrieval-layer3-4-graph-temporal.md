# 检索第③④层：Graph 召回 + Temporal 召回（issue #5）

> 状态：最小可运行落地（SQLite + 标准库，零强制外部依赖）。
> 设计调研与天花板对照见分支 `docs/retrieval-layer34-design` 的 `docs/design-retrieval-layer3-4.md`。

## 1. 补齐了什么

issue #5 指出检索栈只实现了四路召回中的两路：FTS5 精准检索（①）与 TF-IDF/可选 fastembed 向量（②）。本次补齐：

| 层 | 脚本 | 机制 |
|---|---|---|
| ③ Graph | `scripts/06_graph_index.py` | 规则抽取的实体-关系边，双时态有效期窗口，1/2 跳邻域 BFS，边带 `rec_id` 回溯原文 |
| ④ Temporal | `scripts/05_temporal_index.py` | `event_date` 优先、`created_at` 兜底的区间过滤 + `AS OF <date>` 时点切片；失效不删行，写 `t_invalid` 标记 |
| 合并入口 | `scripts/07_recall_time_graph.py` | 一路 CLI 同时跑 temporal / graph / FTS 关键词三路召回，支持 `--json` |

## 2. 表结构（自动建表，旧库无需重建）

旧库只有 `records` / `records_fts`；首次调用任一脚本时自动 `CREATE TABLE IF NOT EXISTS`：

```sql
-- ④ 事实有效期（双时态）
fact_validity(
    fact_id, valid_from, valid_to,        -- T 世界时间：[valid_from, valid_to)，NULL=开放
    trans_from, trans_to,                 -- T' 系统时间：获知 / 判失效
    t_invalid, superseded_by, source_rec_id, note
)

-- ③ 实体结点
entities(entity_id, canonical_name, entity_type, first_seen)

-- ③ 关系边（字段对齐 issue #5 最小契约）
relations(
    rel_id, subject, relation, object,
    valid_from, valid_to,                 -- T 世界时间窗口
    trans_from, trans_to,                 -- T' 系统时间窗口
    t_invalid, fact_text, rec_id,
    extractor, confidence, superseded_by
)
```

失效规则沿用 Graphiti/Zep：旧边保留不删，`valid_to` / `trans_to` 闭合、`t_invalid=1`、`superseded_by` 指向取代边。时点可见性由窗口条件决定，`t_invalid` 只记录“已被取代”这一事实。

## 3. CLI 用法

```bash
# 一次性回填事实有效期 + 抽取图（幂等；--rebuild 清空派生表重建索引）
python scripts/07_recall_time_graph.py --db work/real.db --action build

# 区间过滤（按事实起始日期，两端闭区间）
python scripts/07_recall_time_graph.py --db work/real.db --since 2026-05-01 --until 2026-05-31

# 时点切片：2026-09-15 当天“有效”的事实
python scripts/07_recall_time_graph.py --db work/real.db --as-of 2026-09-15

# 图邻域：Python 结点 2 跳，可叠加谓词 / 时点 / 关键词
python scripts/06_graph_index.py --db work/real.db --action neighbors \
    --entity Python --hops 2 --relation LEARNS --as-of 2026-09-01

# 关键词与时间 / 图过滤组合，JSON 输出
python scripts/07_recall_time_graph.py --db work/real.db \
    --since 2026-09-01 --until 2026-09-30 --keyword Python --json
```

`05_temporal_index.py` 单独提供 `backfill | as-of | range | invalidate` 动作；
`06_graph_index.py` 单独提供 `build | neighbors | recall` 动作。

## 4. 双时钟说明

- `--clock valid`（默认）：回答“世界上那天这件事是不是真的”。
- `--clock transaction`：回答“系统那天已经获知这件事没有”。

PR #37 之后，导出可同时带 `event_date`（世界时间 T）与 `created_at`（入库/提及时间 T'）。回填时 `valid_from = event_date`、`trans_from = created_at`；若 `event_date` 为空或为 `[记忆，待核]`，`valid_from` 存空串而不是伪造提及日期，世界时间查询会跳过它，事务时间仍可见。旧库没有 `event_date` 列时，仍回填 `valid_from = trans_from = created_at`。

## 5. 已知局限（不粉饰）

1. **抽边是规则法，不是 LLM**：实体来自自指结点、引号跨度、可选白名单；关系来自有限中文正则模板（LEARNS / USES / WORKS_AT / LIVES_IN / LIKES / RESPONSIBLE_FOR / PREPARES_FOR）与同记录共现 MENTIONS。**召回率与准确率均未标定**，稀疏模板覆盖不了开放域表述。
2. **跳数范围**：邻域 BFS 只做 1 / 2 跳；没有 community 摘要、没有向量重排、没有 BM25 图内排序。
3. **时间粒度**：`event_date` / `created_at` 是 `YYYY-MM-DD` 日期字符串，无时分秒；不支持相对时间表达式（“上个月”“上周四”）。未知事件时间存空串，不伪装成提及当天。
4. **T 与 T′ 同值**：现有数据无法区分事件发生时间与系统获知时间，迟到事实 / 审计回放只能模拟。
5. **MD5 全内容去重**：同一句话跨日期重复只留第一条，事务时间证据被抹掉；要分析“某说法何时反复出现”需先改去重键。
6. 共现 MENTIONS 是弱信号（窗口 = 单条记录），已限制单记录参与对数并过滤颜色 / CSS / 纯数字等噪声跨度，但仍会混入短语级噪声。
