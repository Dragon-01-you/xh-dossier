# 02 · 浏览器 Agent 的 DOM 导出任务单（零扩展）

> 给任意有浏览器控制能力的 Agent。目标：把本人已登录的豆包会话，导出成 `work/raw/` 下的 Markdown 原件；不安装扩展、不点系统「另存为」。

## 适用边界

- 只导出**你自己账号、自己可见**的会话；不要读别人的聊天、Cookie、密码或验证码。
- 默认只支持豆包；其他平台没有验证，不要猜选择器。
- 登录/验证码/系统弹窗必须交还本人（`interaction.request_action`）。
- 导出的是原件，不让模型先摘要、改写或合并。

## 执行步骤

1. **打开目标会话页**：用本人日常已登录的浏览器（不要用桌面客户端的内嵌浏览器），确认页面已显示完整消息。
2. **确认当前 DOM 契约**：
   - 消息行：`.v_list_row`
   - 角色：行内 `[data-message-role="user"]` / `[data-message-role="assistant"]`
   - 正文：`[data-testid="message_text_content"]`
   - 如果这三个都不存在，停止并报告“站点 DOM 已改版”，不要用旧 `.send-msg-bubble` 硬猜。
3. **执行 `scripts/dom_export.js`**：
   - 有页面求值能力：读取整个文件内容，作为 JS 执行。
   - 没有求值能力：打开 DevTools Console，粘贴整个文件，回车。
4. **两种落盘方式，任选一种**：
   - 下载：默认会触发浏览器原生下载，文件名为 `豆包 - <会话标题>.md`；用浏览器下载记录核对路径。
   - Agent 直写：执行前设 `window.__XH_DOM_EXPORT_NO_DOWNLOAD__ = true`，执行后读 `window.__XH_DOM_EXPORT__.markdown`，写进 `work/raw-doubao-dom/豆包 - <会话标题>.md`。
5. **验收导出文件**：
   - 必须有 `## Metadata`、`## Conversation`；
   - 角色标题只出现 `### 🧑‍💻 User` / `### 🤖 Assistant`；
   - `Message-Count` 与标题数量一致；
   - 不得出现 `11月8日 14:11` 这类时间分隔行（脚本已按角色节点过滤；出现说明选择器漂移）。
6. **送入索引**：

```powershell
python -X utf8 scripts/xh.py ingest --raw work/raw-doubao-dom --db work/unified_index.db --query 口播
```

看到 `INDEX_OK` 即链路可用。注意：单字/空消息（如“哎”）会被 `01` 的正文长度门槛跳过，`total_raw` 可能小于 `Message-Count`，不是导出丢消息。

## 失败处理

- `count=0`：页面未加载、消息未渲染，或选择器改版；先滚动/等待，再检查 `[data-message-role]`。
- 角色全是 Assistant：说明站点移除了角色属性；停止，不要交付错误角色文件。
- 长会话只导出当前 DOM 中已渲染的行：虚拟滚动未覆盖时，先用页面滚动加载更多，或在报告里标 `PARTIAL`，不要声称全量。
- 下载被浏览器拦截：改用 Agent 直写（第 4 步 B），不要反复点。

## 通过标准（给审核人）

- `work/raw-doubao-dom/` 有实际文件，大小 > 0；
- 文件头、角色标题、`Message-Count` 可核对；
- `ingest` 返回 `INDEX_OK` 且查询有命中；
- 报告里写清：页面 URL、导出时间、消息数、文件路径、SHA256、已知局限。
