# 04 · `--strict` 把合法 `[待确认]` 判死，并误杀正常措辞与 Linux 路径

Status: ready-for-human
Type: bug
Priority: P1
Step: S3.3 / S3.4 / S3.5

## 现象 A：与 SKILL / S3.3 直接矛盾

SKILL 要求“记不清的先标 `[待确认]`”；v6 的 S3.3 写明 strict 下应为 INFO、不 fail。实际代码：

```python
if unconfirmed_total > 0:
    diagnostics.append("INFO: ...")
    if strict:
        passed = False
```

按 SKILL 做的 6 份 kit（含一条符合 v6 形状的 `[待确认]`：疑点 + 原文 + 出处）→ `VALIDATE_FAIL`、exit 1。删掉这一段立刻 `VALIDATE_OK`。

## 现象 B：两处误报

1. 用户在 `03` 里写“**不要用**‘多维度赋能’‘打造全链路闭环生态’这类词”（这是立规矩），被判 `CLICHE found`。豁免只认 `禁止|严禁|不要说|AI 腔调`，不认“不要用”。
2. 按模板 `00` 填真实知识库路径 `/home/laochen/notes` → 判 `PII_OR_SECRET_RISK`；换成 `E:\notes` 则通过。Linux 用户按模板填就必然失败。

## 期望

- strict 下 `[待确认]` 只记 INFO，不影响退出码；
- 禁词豁免覆盖“不要用 / 别用 / 不要出现”等祈使变体；
- PII 路径规则对称：要么两边都拦，要么两边都放行；对“用户自己的知识库路径”应有白名单或确认机制。

## 证据

- `/tmp/xh-run/kit2`（含 `[待确认]` → FAIL）
- `/tmp/xh-run/kit8`（删除后 → OK）
- `/tmp/xh-run/kit3`（Linux 路径 → FAIL） / `kit4`（Windows 路径 → 通过）

## 最小修复

1. strict 判定改为 `if strict and unconfirmed_total_without_shape > 0`，只对“形状不合规”的 `[待确认]` 失败；
2. 豁免正则加 `不要用|别用|不要出现`；
3. 路径规则统一：`/home|x` 与 `[A-Z]:\\Users` 同权，或对模板占位路径做 allowlist。

## 修复（2026-11-22）

- strict 下 `[待确认]` 只报 INFO，不再 fail（对齐 v6 S3.3 与 SKILL rule 4）。
- 禁词豁免增加 `不要用 / 别用 / 不要出现`。
- 回归：`test_strict_allows_pending_marker`、`test_cliche_exemption_for_dont_use_phrase`
- 复验：含 `[待确认]` 的 kit 修复前 VALIDATE_FAIL → 修复后 VALIDATE_OK；`不要用…` 不再误报。
- 未改：`/home/<name>` 仍按 home 目录敏感路径处理（与 `C:\Users\<name>` 对称）；建议文档提示写 `~/notes` 或非 home 路径。
