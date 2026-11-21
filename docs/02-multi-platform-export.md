# Stage 2 · 多平台聊天记录原件导出与浏览器开关指南

> **核心原则：只拿带原文和时间的原件，绝不让 AI 提前摘要覆盖原文。**
> 所有导出的文件统一放进仓库忽略的 `raw/` 目录（只读底账），绝不提交到 Git。

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
