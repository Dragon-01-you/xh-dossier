# 02 · GBK / UTF-16 导出被静默写成乱码，仍报 INDEX_OK

Status: ready-for-human
Type: bug
Priority: P0
Step: S5.8

## 现象

把 4 个文件放进 `raw/`：合法 UTF-8、GB18030、UTF-16、JSONL。跑 `01`：

```text
INDEX_OK total_raw=13 dedup_skipped=0 indexed=13
```

但库内：

```text
REC-0011  gbk_export.md    '�Ұ�����˵�����������ص�˵���˻ص�'
REC-0013  utf16_export.md  'unknown'  '��#'
```

乱码还会继续进入 `02` 的“话题簇 #4”，展示给用户。

## 根因

`path.read_text(encoding="utf-8", errors="replace")` 把无法解码的字节替换成 U+FFFD，既不报错也不计数。

## 证据

- `/tmp/xh-run/evidence/s5-s6-error-paths.txt`
- 文件用 `file` 确认为 `ISO-8859 text` 与 `UTF-16, little-endian`

## 期望

- 依次尝试 utf-8-sig / utf-8 / gb18030 / utf-16；
- 全部失败时跳过该文件并累计 `decode_failed`，最终输出 `DECODE_PARTIAL` 或 `DECODE_FAILED` + 非零（按严重度）；
- 任何情况下不得把 U+FFFD 写进 `records`；
- 报告里出现乱码应视为失败，而不是“话题簇”。

## 最小修复

1. 新增 `read_text_with_detection(path)`；
2. 三个 fixture（GBK / UTF-16 / BOM）进 CI，断言不出现 `\ufffd`；
3. 输出 `ENCODING_REPORT`（成功/跳过/失败文件清单）。

## 修复（2026-11-22）

- `read_text_detected()`：BOM → UTF-8 → UTF-16（含无 BOM 的 NUL 启发）→ GB18030；失败计入 `decode_failed` 并跳过，不再 `errors="replace"`。
- `INDEX_OK` 增加 `decode_failed` / `zip_extracted`；有文件无法解码时打印 `WARN_DECODE_FAILED`。
- 回归：`tests/test_cold_start_fixes.py::test_gbk_and_utf16_exports_are_decoded`
- 复验：修复前 GBK/UTF-16 入库为乱码 → 修复后正确中文，U+FFFD 计数为 0。
