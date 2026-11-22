# 03 · “导出全部”得到 zip 后无法入库；缺 DB/坏 schema 仍裸 traceback

Status: needs-triage
Type: bug
Priority: P1
Step: S4.3 / S5.3 / S6.2

## 现象 A：批量 zip 断路

AfterChat 的“导出全部”得到 `all_afterchat.zip`（773 bytes，内含 1 个 .md）。放进 `raw/` 后跑 `01`：

```text
INDEX_EMPTY: 未在 ... 找到可索引的 .json/.jsonl/.md/.txt 记录（total_raw=0）
EXIT=2
```

`01` 只处理 `.json/.jsonl/.md/.txt`，`.zip` 被静默跳过；错误提示也没提 zip。用户按文档“全部导出”必然卡住。

## 现象 B：缺 DB / 坏 schema 裸 traceback

```text
FileNotFoundError: Database not found: work/nope.db
sqlite3.OperationalError: no such table: records
```

exit 1，但无 `FOUR_WAY_DB_NOT_FOUND` 之类的专属 marker。

## 期望

- `01` 遇到 `.zip`：自动解包到临时目录再索引，或明确输出 `ZIP_NEEDS_UNZIP` + 解压命令；
- `02` 缺 DB → `FOUR_WAY_DB_NOT_FOUND` + exit 2，无 traceback；
- `02` schema 不对 → `FOUR_WAY_BAD_DB` + 提示先跑 `01`。

## 证据

- `/tmp/xh-run/evidence/s5-s6-error-paths.txt`
- zip 产物 `/tmp/xh-run/all_afterchat.zip`

## 最小修复

1. `01` 增加 zip 分支（`zipfile` 标准库，解包到 `work/_unzipped/`）；
2. `02` 在 `sqlite3.connect` 后先 `PRAGMA table_info(records)`，缺失即给专属 marker；
3. 两个失败 fixture 进 H2 清单。
