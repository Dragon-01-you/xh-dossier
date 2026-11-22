# 兜底导出：无扩展的浏览器 DOM 导出（豆包）

> 状态：**已在真实登录态环境跑通**（2026-11-23，L1 证据）。
> 适用对象：没有安装 ScriptCat/浏览器扩展、没有 AfterChat 导出入口，或者 Agent 只能控制浏览器（不能替用户点“另存为”）的场景。
> 与 AfterChat 的关系：AfterChat 是**首选**路径（原文最完整）；本文是**兜底**路径（可被 Agent 全自动执行）。

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
2. Agent 通过浏览器控制读取消息列表：按 `.v_list_row` 逐行取每条消息，识别角色（用户 / 助手），把正文按 Markdown 段落还原。
3. 组装成单文件 Markdown，带 Metadata 头（Source URL / Time / Exporter），落盘到 raw 目录：

```
raw-doubao-dom/
└── 豆包 - 字节跳动旗下 AI 智能助手.md
```

4. 交给 Stage 3 索引：

```bash
python -X utf8 scripts/01_clean_and_index.py --raw <dom导出目录> --db <输出库> --query <验证词>
```

> 说明：本文件只记录**已验证的选择器与产物形状**（`.v_list_row`），不二次发明滚动/分页/附件选择器；具体角色判定与清洗细节以导出实现的代码为准。

## 4. 真实验证证据（2026-11-23）

- 导出文件：`D:\xh_auto\xh-runs\browser-e2e\raw-doubao-dom\豆包 - 字节跳动旗下 AI 智能助手.md`
  - 大小 **20,139 bytes**，148 行；
  - 结构：`## Metadata` → `## Conversation` → 4 条消息（`### 🧑‍💻 User` L10 / `### 🤖 Assistant` L85 / `### 🧑‍💻 User` L103 / `### 🤖 Assistant` L114）。
- 索引结果（`D:\xh_auto\xh-runs\browser-e2e\01-dom.log`）：

```
INDEX_OK total_raw=4 dedup_skipped=0 indexed=4
QUERY '世界指南' -> 2 hit(s)
  [REC-0001 | said=2026-11-23 | event= | unknown] ...
  [REC-0002 | said=2026-11-23 | event= | unknown] ...
```

即：DOM 导出 → Stage 3 索引 → 关键词召回，全链路可用。两行 `event=` 都为空、`date_kind=unknown`，这是 PR #37 修复后的预期行为：普通工作指令和助手交付说明都不是“当天发生的事件”，不再把 `created_at` 复制成事件时间，不是导出丢失。

## 5. 已知局限（不要当成 AfterChat 的等价替代）

- 只验证了**豆包**一种站点；微信、Kimi、DeepSeek 等站点的 DOM 结构未验证（UNVERIFIED）。
- 长会话的虚拟滚动 / 折叠消息：本次样本只有 4 条消息，**未验证**大段会话是否会被截断。
- 附件、图片、语音等非文本消息：本次样本不含，**未验证**还原方式。
- DOM 选择器（`.v_list_row`）属于**外部契约**，站点改版即失效；失效时回退到 AfterChat。
- 导出文件是“原件”，只读；不要让它覆盖个人档案，也不要让模型先改写再落盘。

## 6. 与 issue / PR 的关系

- 本文补的是 Stage 2 的**第三条路径**，不改变 AfterChat 的既有说明（issue #4 / #7，PR #41 的范围不变）。
- 对应的跟踪 issue 见仓库 issue 列表；DOM 导出脚本与选择器若后续产品化，应另有测试防止选择器漂移。
