# Stage 2 · 多平台聊天记录原件导出与浏览器开关指南

> **核心原则：只拿带原文和时间的原件，绝不让 AI 提前摘要覆盖原文。**
> 所有导出的文件统一放进仓库忽略的 `raw/` 目录（只读底账），绝不提交到 Git。

---

## 〇、先分清「引擎」和「工人」——最常见的认知错误（实测补充）

**很多人装完扩展点导出没反应，是因为少装了一样东西。** 这里必须分清两层：

| 层 | 是什么 | 作用 |
|---|---|---|
| **脚本管理器（引擎）** | ScriptCat 脚本猫 / Tampermonkey 油猴 / Violentmonkey 暴力猴 | 只是能运行小工具的底座，**它本身不导出任何东西** |
| **用户脚本（工人）** | AfterChat 等 | 真正干活：抓取对话、写成 Markdown/ZIP |

**只装引擎、不装脚本 = 买了打印机没装驱动，点什么都没反应。**

### 0.1 装哪个导出脚本？按你要导出的平台选（不要写死一个）

| 你要导出的平台 | 推荐脚本 | 出处 |
|---|---|---|
| **多平台（默认推荐）** | **AfterChat** — 支持约 30 个平台（ChatGPT / Claude / Gemini / DeepSeek / GLM / 千问 / Kimi / 豆包 / 腾讯元宝 / 腾讯 ima / Copilot / Grok / Poe / Perplexity / MiniMax / Mistral / Google AI Studio …），单条+批量+项目导出、增量导出、保留思考过程 | **GreasyFork #589622** https://greasyfork.org/zh-CN/scripts/589622-afterchat-llm-chat-exporter （**注意：它不在 ScriptCat 脚本中心，搜 AfterChat 搜不到**） |
| 只有 Claude / ChatGPT / Gemini / Grok | AI Chat to Markdown #8113（4 平台） | ScriptCat 脚本中心 |
| 知识库用 Obsidian | ChatGPT to Obsidian #5715 | ScriptCat 脚本中心 |

安装 AfterChat：打开 GreasyFork 页面 → 点"安装此脚本" → 确认弹窗点确认 → 打开任意 AI 网站，**右下角出现白色圆形下载按钮 = 脚本已激活**。若没出现：检查下列 MV3 开关、确认脚本是"启用"状态、`Ctrl+F5` 强刷新几次。

### 0.2 导出的两种范围——选错场景导不出你要的东西（实测）

- **只导当前一个对话 → 单个 `.md`**：在**某个对话页面**点右下角白色按钮。
- **导出全部对话 → 一个 `.zip`**：回到 AI 网站的**首页 / 对话列表页**（不是某个具体对话）再点按钮。运行时会显示 `4/331` 这样的进度。

**⚠️ 批量导出的隐藏确认门（实测未闭环，Issue #7）**：真实登录态下，批量进度曾出现 **`331 → 56/331` 回退、反复循环、始终不出 zip** 的现象。推断是批量流程中有一个**未文档化的用户确认弹窗**（或平台限流/风控），未确认就静默重来。**遇到进度回退：留意页面上有没有需要你确认的弹窗，手动确认；若反复失败，改用"逐条导出"或分批。** 该流程尚未在账号本人在场的情况下完整闭环，不要当成"跑完 331 就一定打包成功"。

### 0.3 文件存哪里——不要假设固定目录（实测）

- AfterChat 用浏览器原生下载（`@grant none`，无自定义保存路径配置），所以**遵守浏览器的下载设置**。
- 如果浏览器开了「下载前询问保存位置」（Edge: `prompt_for_download=true`），导出完成后会弹 **Windows「另存为」系统弹窗**，需要你**亲自选文件夹并点保存**。AI/扩展碰不到系统弹窗——这就是"进度跑完却一直不出文件"的真实原因。
- 若没开该设置，文件进浏览器默认下载目录（可在浏览器设置里改）。
- **务必用 `Ctrl+J` 打开下载记录确认文件是否落地、落在哪里。不要写死任何固定路径。**

> 链路说明（#92）：仓内已无本机接收服务（旧 `127.0.0.1:8765` POST 落点已删除）。当前只有两条落盘替代链路：本条的**扩展原生下载**，以及 `docs/fallback-dom-export.md` §7 的 **Agent 读 DOM 写 `work/raw/`**；两条链路的真机落地都待真人复核，状态见该文件「未真机验证边界」。

### 0.4 新手零基础路径（推荐）

1. 用你**平时已经登录聊天平台的那个浏览器**（Edge / Chrome 均可），不要换全新无登录态的浏览器；
2. 按第一节装 **ScriptCat（脚本猫）**，再按第二节装 **AfterChat** 用户脚本；
3. 打开要导出的对话页，点右下角白色下载按钮；
4. 弹出系统「另存为」时本人选目录保存，然后 `Ctrl+J` 核对落盘。

**不要用桌面 AI 客户端自带的内置浏览器（IAB / 内嵌浏览器）做导出**：这类内置浏览器通常不复用你本机 Edge / Chrome 的登录态，进去往往是未登录状态，会看到“请去另一台电脑继续”之类提示，导不出真实会话。导出必须在你平时已经登录聊天平台的那个扩展浏览器里完成；如果已经在客户端内置浏览器里卡住，退回本机日常浏览器按上面 1~4 步重做。

---

## 一、推荐导出扩展（ScriptCat 脚本猫）与浏览器开关必做设置

很多网页版对话没有内置一键 Markdown/JSON 导出按钮，推荐使用开源用户脚本管理器 **ScriptCat（脚本猫）** 配合对话导出脚本导出聊天原件。**如果装完扩展点导出没反应或读取不到页面/本地路径，90% 是没开 MV3 扩展开关：**

### 0. 官方安全获取方式（经本人确认后再打开/下载）

- **脚本猫官网 & 脚本中心**：https://scriptcat.org （使用文档：https://docs.scriptcat.org ）
- **Microsoft Edge 加载项商店**：https://microsoftedge.microsoft.com/addons/detail/liilgpjgabokdklappibcjfablkpcekh
- **Google Chrome 扩展商店**：https://chromewebstore.google.com/detail/hompjdfbfoggjbeebconmlijpelpfapo
- **GitHub 开源发布页**：https://github.com/scriptscat/scriptcat/releases

也可以直接运行仓库内置的交互式同意门禁向导，确认后自动为你打开官方商店页或拉取开源压缩包并打印开关自检清单：
```bash
# 先同意确认，再按指引跳转安装（支持 --browser edge|chrome|site 或 --download-release）
python -X utf8 scripts/00_export_wizard.py --browser edge
```

### 操作步骤（Chrome / Edge 通用）

1. 在浏览器地址栏输入并进入扩展管理页：
   - Chrome：`chrome://extensions`
   - Edge：`edge://extensions`
2. 打开右上角 **「开发者模式（Developer Mode）」** 开关。
3. 找到已安装的 **「脚本猫（ScriptCat）」**，点击卡片右下方的 **「扩展详细信息 / 详情（Details）」**。
4. 进入详情页后，向下滚动并**确认打开以下关键开关**：
   - ✅ **「允许运行用户脚本（Allow User Scripts）」**（新版浏览器 MV3 强制要求手动开启，否则脚本完全不触发）
   - ✅ **「允许访问文件网址（Allow access to file URLs）」**（如需导出本地预览或读取本地辅助脚本）
   - ✅ 如页面有“固定在工具栏”，建议顺手打开方便一键触发导出。
5. 返回原本的 AI 对话网页**强刷新一次（`Ctrl + F5`）**，再点导出保存为 `.json` 或 `.md` 放入 `raw/`。

> **为什么一定要强调这一步？**
> 因为很多工具人教程默认你扩展已经能跑，结果新手装完扩展点十次都没反应，以为脚本坏了，实际只是扩展「详细信息」里的「允许运行用户脚本 / 开发者模式」开关没拧开。

### 怎么确认开关真的打开了（自检，不是照着点一遍）

照步骤开完后，按下表逐项核对；任一项对不上，脚本都不会触发：

| 检查项 | 怎么算通过 |
|---|---|
| 开发者模式 | 扩展管理页右上角「开发者模式」开关处于打开状态 |
| 允许运行用户脚本 | ScriptCat 详情页该开关为打开；打开 ScriptCat 管理器，能看到 AfterChat 且状态为「启用」 |
| 允许访问文件网址 | 详情页该开关为打开（需要读取本地文件时才必需） |
| 页面已加载脚本 | 回 AI 对话页按 `Ctrl + F5` 强刷，右下角出现白色圆形下载按钮；没有按钮 = 上面某一项没生效，回去逐项复查 |

---

## 二、常见多平台导出清单（统一放进只读 `raw/`）

| 来源类型 | 推荐导出方式与格式 | 保留关键字段 | 放哪里 |
|---|---|---|---|
| **网页端 AI**（ChatGPT / DeepSeek / 豆包等） | 官方设置导出全量 `conversations.json`，或开好上述浏览器扩展开关后逐条导出 `.md` / `.json` | 原始时间、用户/AI 角色、原话一字不改 | `raw/web/` |
| **本地 AI CLI / 桌面端**（Claude Code / Codex / Cursor / Antigravity / Gemini CLI 等） | 复制本地会话导出的 `.jsonl` / `.md` 归档（或由脚本解析成标准记录） | 会话时间、工具动作与用户纠正原话 | `raw/local/` |
| **碎片记录 / 语音转写**（flomo / 笔记导出的备忘 / 语音备忘录） | 批量导出 `.md` / `.txt` | **务必保留“当时口述”与“事后追忆”时间差** | `raw/notes/` |

---

## 三、导出后的多 Agent 识别与清洗接力（下一阶段）

1. 不要人工去翻几千份 JSON 或 HTML，也不要直接扔给大模型压缩。
2. 直接进入 Stage 3：
   ```bash
   # 1) 剥壳清洗 + 全文 MD5 去重 + 建 SQLite FTS5 非向量冷库
   python -X utf8 scripts/01_clean_and_index.py --raw raw/ --db work/unified_index.db

   # 2) 运行四路匹配（关键词 + 向量语义 + 去均值聚类 + 模式磁铁与主宾/否定防坑过滤）
   python -X utf8 scripts/02_four_way_match.py --db work/unified_index.db --out work/backfill_candidates.md
   ```
3. 把生成的 `work/backfill_candidates.md` 与采访初稿对比，手工把核实无误的条目录入 6 份模板、删掉 `[待确认]`，即大功告成。
