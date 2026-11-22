# 冷启动实测 · 2026-11-22

Status: needs-triage
Type: research
Scope: 以“零环境新用户”身份，从 clone 跑到发布门禁；不修改生产代码。

## 结论

- 全链路可以跑完，但 **Stage 3 在非 AfterChat 格式的真实导出上会产出错误档案**，且 `INDEX_OK` 不报错。
- 浏览器段已真实跑通：Chrome for Testing 159 + ScriptCat 1.5.2 + AfterChat 1.25.0，导出 773 字节 MD，`01` 入库 6 条（3 user / 3 assistant，0 unknown）。
- 发布面仍为空：无 `pyproject.toml`、无 tag/release、无 `VERSION/CHANGELOG/known-limits/SHA256SUMS`、CI 仅 ubuntu+3.12 且不跑 `--strict`。

## 证据索引（原始输出在 /tmp/xh-run/evidence/）

| 文件 | 内容 |
|---|---|
| `s0-baseline.txt` | Ubuntu 24.04 / Python 3.14.8 / 无浏览器 |
| `s0-network.txt` | GitHub 200；Chrome 商店与 Greasyfork SSL 不通；Edge 商店 200 |
| `s1-readme-demo.txt` | README 四步在作者样例上全绿 |
| `s1-failpaths.txt` | 无 doctor、`pip install .` 失败、无 tag |
| `s2-interview-transcript.md` | 6 轮访谈（simulated persona） |
| `s5-s6-error-paths.txt` | 缺 raw / 空 raw / 空 DB / 坏 schema |
| `final-verify.txt` | CI 矩阵、发布要件、H4 检查 |

关键产物校验和：

- AfterChat 1.25.0 脚本：`cd99b812584189f4c6ef63ef9af9a583a3b0b4bd98509859388b36d7553955a5`
- AfterChat 真实导出：`f6e091ff9577a2c1886cabc6a20461ce4d0696a859fa7cbf4c67a1baa1896028`（773 bytes）
- 替代导出器产物：`1f5b5538e5b48693d8dbff92b457541ed4f18fe1ed67408f4578c30c4e270c7c`（783 bytes）

## 补充：真实登录态内容（2026-11-22 21:50）

- 登录成功（账号名已脱敏）；打开的真实会话《豆包CLI安装失败解决》**只有 2 条消息**。
- 宿主浏览器限制：扩展商店 `ERR_CONNECTION_CLOSED`；任意下载 `ERR_ABORTED`。因此**无法取回真实导出文件**。
- 改用 live DOM 抽取真实文本 + 重建 AfterChat 容器（不是真实导出产物）：
  - 文件 SHA256 `c61dc04988f7129b669b00da716bf944fdeffb285918764d15bb1d6e5efd0533`
  - `01`：2 条，1 user / 1 assistant，0 unknown
  - `02`：`FOUR_WAY_OK records=2`，但 Way 1 / Way 3 / Way 2&4 **全部 0 候选**
- 结论：低样本下 `FOUR_WAY_OK` 仍被打印，与 CLOUD-06 一致；真实数据没有让它变好。

## 复现前提

- AfterChat 源码取自官方仓库 `AfterThink/AfterChat-Script`（AGPL-3.0），因 Greasyfork 在该网络不可达。
- 浏览器导出使用 mock DeepSeek 会话（L2），真实登录导出仍需 L4 用户在场。
- Windows 双平台未测（由用户本地负责）。
