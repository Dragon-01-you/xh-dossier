# 01 · 真实导出解析只认 AfterChat 格式，其他导出器会把 AI 回复记成用户发言

Status: needs-triage
Type: bug
Priority: P0
Step: S5.2

## 现象

用 ScriptCat 商店可安装的 `DeepSeek Chat Exporter 1.6.0` 导出真实文件，再跑：

```bash
python -X utf8 scripts/01_clean_and_index.py --raw <dir> --db <db>
```

输出 `INDEX_OK`、exit 0，但入库结果：

- 7 条记录 **全部 `role=user`**（AI 回复被记成用户说的）；
- 6/7 条 `created_at=unknown`（文件头有 `- **Date**: 11/22/2026`）；
- 标题行、URL 行被当成一条记录；
- 代码围栏 ````text` 原样入库。

## 根因

`01_clean_and_index.py` 的真实导出判定是硬编码：

```python
real_export = "## Conversation" in text and ("🧑‍💻 User" in text or "🤖 Assistant" in text)
```

只匹配 AfterChat 输出。其他导出器落到通用分支，角色与时间全部丢失。

## 证据

- 输入：`/tmp/xh-run/export/预约小程序联调.md`（783 bytes，SHA256 `1f5b5538…70c7c`）
- 输出：7 条全 user，见 `spec.md` 证据索引
- 对照：AfterChat 1.25.0 导出的 773 bytes 文件入库 6 条，3 user / 3 assistant，0 unknown

## 期望

- 识别 `## 🧑 User` / `## 🤖 <任意平台名>` 这类导出；
- 解析 `- **Date**:`（M/D/YYYY）与 `- **Time:**`（YYYY-MM-DD HH:MM:SS）两种时间；
- 无法判定角色时显式报 `ROLE_UNKNOWN` 并计数，不得默认成 user 静默入库；
- 标题/URL 行不入库。

## 最小修复

1. 把“真实导出识别 + 角色解析”抽成独立函数，按“格式指纹”匹配多个导出器；
2. 加两个真实 fixture（AfterChat / 替代导出器）进 CI，断言 role 分布与 unknown=0；
3. 未识别格式时输出 `EXPORT_FORMAT_UNKNOWN` + 可操作提示，禁止静默走通用分支。
