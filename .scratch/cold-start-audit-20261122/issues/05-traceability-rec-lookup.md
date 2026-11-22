# 05 · 追溯链断裂：报告给了 `[REC-xxxx]`，却没有取回全文的入口

Status: needs-triage
Type: bug
Priority: P1
Step: S6.6

## 现象

`02` 产出的 `backfill_candidates.md` 里：

- 候选摘录被截断到 160 字（Way 1 是 100 字，簇示例 75 字）；
- 全仓没有 `--rec` / `--show` 之类的查询入口；
- `REC-xxxx` 按插入顺序分配：语料新增一条更早的记录，原来 `REC-0001` 的内容就变成 `REC-0002`。

而 `04` 模板要求用户“抽回 `[REC-xxxx]` 原文再转正”。当前用户只能自己打开 SQLite 查。

## 期望

- 新增 `python -X utf8 scripts/01_clean_and_index.py --db <db> --rec REC-0002`，打印完整原文 + `source_file` + `created_at` + `role` + md5；
- 报告里的候选附 `md5` 或稳定 id，跨重跑不变；
- 截断处标注“已截断，用 `--rec` 看全文”。

## 证据

- `/tmp/xh-run/work/backfill.md`
- 重跑实验：新增一条更早记录后 `REC-0001` 指向另一条内容

## 最小修复

1. `rec_id` 改为 `REC-` + content md5 前 8 位（冲突再加序号）；
2. `01` 增加 `--rec` 输出；
3. 报告每条候选带稳定 id 与“查看全文”的命令示例。
