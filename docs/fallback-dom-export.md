# 兜底导出：无扩展的浏览器 DOM 导出（豆包）

> 状态：**已在真实登录态环境跑通（2026-11-24，豆包主对话；8 条消息 / 4,670 bytes 浏览器下载）**。
> 适用对象：没有安装 ScriptCat/浏览器扩展、没有 AfterChat 导出入口，或者 Agent 只能控制浏览器（不能替用户点“另存为”）的场景。
> 与 AfterChat 的关系：AfterChat 是**首选**路径（原文最完整）；本文是**兜底**路径（可被 Agent 全自动执行）。
> 重要更新（2026-11-24）：豆包当前 DOM 已没有稳定的 `.send-msg-bubble` 用户标记；角色以行内 `[data-message-role="user"|"assistant"]` 为准，正文以 `[data-testid="message_text_content"]` 为准。旧选择器不要再用。

## 1. 为什么需要这条路径

Stage 2 的标准路径是“浏览器扩展 / AfterChat 导出原件”（见 `docs/02-multi-platform-export.md` 与 README Stage 2）。
但真实环境里常见两种卡点：

1. 用户是零配置小白，装扩展、开“允许运行用户脚本 / 允许访问文件网址”就卡住；
2. 导出需要“另存为”这种必须人点鼠标的交互，Agent 无法独立闭环（issue #7 的 L4 证据）。

DOM 导出补的正是这两块：**登录态由用户提供，读取与落盘由 Agent 完成**，不需要扩展，也不需要点“另存为”。

## 2. 与 AfterChat 的对比

| 维度 | AfterChat（首选） | DOM 导出（兜底） |
|---|---|---|
| 前置条件 | 安装扩展/脚本，开两个开关，强刷页面 | 只要浏览器已登录对应站点 |
| 谁来完成 | 用户点导出 / 另存为 | Agent 直接读 DOM 并写文件 |
| 原文完整度 | 高（接近原始消息） | 中（受渲染影响：折叠、虚拟滚动、附件可能缺失） |
| 稳定性 | 依赖站点导出功能 | 依赖 DOM 结构，选择器可能随站点改版失效 |
| 适合场景 | 一次性完整归档 | 小白零配置、Agent 自动化、快速拿到可用原文 |

## 3. 真实操作路径（已验证）

1. 用户在 in-app 浏览器里登录豆包，打开目标会话页。
2. Agent 通过浏览器控制读取消息列表：按 `.v_list_row` 逐行取每条消息，用行内 `[data-message-role]` 识别 `user` / `assistant`，正文取 `[data-testid="message_text_content"]`，组装成 Markdown。
3. 执行 `scripts/dom_export.js`；它会生成 AfterChat 兼容的 Markdown，存入 `window.__XH_DOM_EXPORT__`，并默认触发浏览器原生下载（或设 `window.__XH_DOM_EXPORT_NO_DOWNLOAD__ = true` 由 Agent 直写）。
4. 产物落到 raw 目录：

```
raw-doubao-dom/
└── 豆包 - <会话标题>.md
```

5. 交给 Stage 3 索引：

```bash
python -X utf8 scripts/01_clean_and_index.py --raw <dom导出目录> --db <输出库> --query <验证词>
```

> 说明：本文件记录的是当前已验证的 DOM 契约；`.send-msg-bubble` 是旧版标记，已不能作为角色依据。站点改版时先检查 `[data-message-role]`，失效就停下，不要猜。

## 4. 真实验证证据

### 2026-11-24（当前 DOM，主对话）

- 页面：`https://www.doubao.com/chat/38414470641333250`（豆包主对话，本人已登录）
- DOM 行：11 个 `.v_list_row`；脚本导出 **8 条消息**（过滤了时间分隔行和单字消息）
- 角色：`[data-message-role]` 逐个识别，8 条标题为 4 个 User / 4 个 Assistant；没有把用户消息误标成 Assistant
- Agent 直写：`work/raw-doubao-dom/豆包 - 主对话.md`，4,709 bytes
- 浏览器原生下载：`C:\Users\ASUS\Downloads\豆包 - 主对话.md`，4,670 bytes；`bu.wait_for_download` 返回 `state=completed`，无「另存为」弹窗
- SHA256：`9F2EE00FC2E29AAA09B6571237FC4DE25A0A1DA4B195E616CB0A60AC42E9CBC7`（下载文件；副本见 `work/evidence/dom-download-20261124.md`）
- 索引：`INDEX_OK total_raw=7 ... indexed=7`；单字“哎”被 `01` 的正文长度门槛跳过，不是导出丢消息
- 查询：`QUERY '口播' -> 4 hit(s)`

### 2026-11-23（旧 DOM，4 条消息）

- 导出文件：`work/raw/豆包 - 字节跳动旗下 AI 智能助手.md`，20,139 bytes，148 行；
- 结构：`## Metadata` → `## Conversation` → 4 条消息；
- 索引结果：`INDEX_OK total_raw=4 dedup_skipped=0 indexed=4`。

> 旧记录只作为历史证据，不再作为当前选择器依据：2026-11-24 复测已确认 `.send-msg-bubble` 不存在。

## 5. 已知局限（不要当成 AfterChat 的等价替代）

- 只验证了**豆包**一种站点；微信、Kimi、DeepSeek 等站点的 DOM 结构未验证（UNVERIFIED）。
- 长会话的虚拟滚动 / 折叠消息：本次真实样本 11 行 / 8 条消息，页面已全部渲染；**更长会话是否只导出当前渲染窗口未验证**。出现 `PARTIAL` 时必须标注，不能声称全量。
- 附件、图片、语音等非文本消息：本次样本不含，**未验证**还原方式。
- DOM 选择器（`.v_list_row` / `[data-message-role]` / `[data-testid="message_text_content"]`）属于**外部契约**，站点改版即失效；失效时回退到 AfterChat 或停止，不要猜旧选择器。
- 导出文件是“原件”，只读；不要让它覆盖个人档案，也不要让模型先改写再落盘。

## 6. 与 issue / PR 的关系

- 本文补的是 Stage 2 的**第三条路径**，不改变 AfterChat 的既有说明（issue #4 / #7，PR #41 的范围不变）。
- 对应的跟踪 issue 见仓库 issue 列表；DOM 导出脚本与选择器若后续产品化，应另有测试防止选择器漂移。

## 7. 本机接收链路已移除（#92）

> 现状：仓内**不再提供**页面 → 本机 HTTP 接收器 / POST 落点（旧 `127.0.0.1:8765` 方案已删除）。不要在脚本、扩展或文档里复活本机端口接收；仓内 `scripts/` 已无 `localhost` / `127.0.0.1` / `receiver` 残留。

### 替代链路 A：扩展原生下载（首选）

- 走 AfterChat / 脚本调用浏览器**原生下载**，由浏览器把文件落到下载目录；见 `02-multi-platform-export.md` §0.1 / §0.4。
- 落盘位置以浏览器下载记录（`Ctrl+J`）为准，**不写死目录**；系统另存为弹窗由本人处理。

### 替代链路 B：Agent 读 DOM 写 `work/raw/`（本文兜底）

- 见 §3：Agent 在已登录会话页读取消息行，按 AfterChat 兼容格式组装 Markdown，直接写到 `work/raw/`，不经页面 → 本机 fetch；再用 `01_clean_and_index.py` 索引复核。

### 未真机验证边界（2026-11-24 更新）

- 链路 B（Agent DOM 直写 + 浏览器原生下载）已在豆包主对话真机跑通：8 条消息、4,670 bytes 下载、索引 7 条；
- AfterChat 扩展已在本地 Edge 真实安装（Tampermonkey 5.5.1 + AfterChat 1.24.2），点击导出后生成 `豆包.md`，但浏览器弹出“打开 / 另存为 / 保存”的落盘确认，仍需本人点一下；**扩展的无人值守落盘未闭环**；
- 微信 / Kimi / DeepSeek 等其他站点 UNVERIFIED；
- 虚拟滚动长会话、附件未验证；
- 失败复核位置：下载记录 `Ctrl+J`；DOM 失效看 `[data-message-role]`；索引复核看 `01` 的 `INDEX_OK` 与查询命中数。
