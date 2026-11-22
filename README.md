# XH-Dossier · 跨平台 AI 入职说明书全流程开源包

> 把散落在二三十个聊天窗口里的 Context（眼前临时桌面），收敛为随身携带的 **6 份可迁移个人 Memory（入职档案）**。  
> 适用于 **任何本地 Agent**（Antigravity / Claude Code / Codex / Cursor / Hermes）以及 **网页端对话模型**（豆包 / DeepSeek / ChatGPT / Kimi）。

[![CI](https://github.com/Dragon-01-you/xh-dossier/actions/workflows/ci.yml/badge.svg)](https://github.com/Dragon-01-you/xh-dossier/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-gray)](LICENSE)

---

## 一、为什么常有人疑惑“到底是 5 份还是 6 份”？

```text
整套说明书 = 1 份 AI 总规矩 + 5 份个人核心档案（共 6 份文件）
  ├── AGENTS.md                 ← 给 AI 看的合作站位、防瞎编底线与工作协议
  └── 5 份个人核心档案（00~04）
        ├── 00-总入口索引.md    ← 读取顺序 + 外部知识库指向
        ├── 01-身份与当前主线.md ← 稳定个人事实 + 当前专注主线 + 彻底放弃项
        ├── 02-核心判断准则.md   ← 遇事怎么取舍（全包最核心的一份）
        ├── 03-硬规则与表达黑话.md ← 说话习惯 + 常见别名/语音口误词典
        └── 04-正反例避坑账.md   ← 试过有效的正例 + 必拦截的真实踩坑反例
```

> 使用网页版 AI（只支持单框系统提示词）时，`AGENTS.md` 常贴入系统设定，正文档案则是那 `5` 份；放到本地 Agent 仓库里完整加载则是 **6 份文件**。

---

## 二、完整四步落地流水线

```text
[1. 访谈立底盘]        [2. 多平台原件导出]       [3. 去重与四路匹配回填]      [4. 校验并跨端挂载]
  skills/               docs/02-...md            scripts/01 + 02              templates/ + 03_validate
  + prompts/01          ⚠️开扩展开发者模式         关键词+向量+去均值聚类        输出可直接交给任何 AI
  先人工拍板基准坐标 ──▶ 原文只读存 raw/      ──▶ +主宾/否定防误报抽样核对 ──▶ 挂载使用、持续微调
```

### Stage 1：结构化访谈立底盘（先人拍板，再查旧账）
- **本地 Agent 用户**：加载 [skills/onboarding-interviewer/SKILL.md](skills/onboarding-interviewer/SKILL.md)，每次 3 个问题，**6 轮**生成初稿（6 轮分别对应 `AGENTS.md` + `00~04` 六份文件）。
- **网页端用户**：复制 [prompts/01_web_ai_interviewer.md](prompts/01_web_ai_interviewer.md) 里的 10 行提示词直接发给豆包 / DeepSeek。

### Stage 2：多平台聊天记录导出（内置 ScriptCat 脚本猫向导 + 开关避坑）
详见 [docs/02-multi-platform-export.md](docs/02-multi-platform-export.md)，或先运行仓库内置的同意门禁引导脚本 `python -X utf8 scripts/00_export_wizard.py --browser edge` 获取开源扩展 **ScriptCat（脚本猫）** 官方安装入口。  
**⚠️ 浏览器扩展/脚本导出最容易卡住的一步**：
1. 打开浏览器扩展管理页（`chrome://extensions` 或 `edge://extensions`）→ 打开右上角 **「开发者模式」**；
2. 点击 **ScriptCat（脚本猫）** 的 **「扩展详细信息 / 详情」**；
3. 打开 **「允许运行用户脚本（Allow User Scripts）」** 与 **「允许访问文件网址」** 开关，返回聊天页强刷即可导出原件进 `raw/`（只读不动，绝不提前让大模型写摘要覆盖原文）。

### Stage 3：多 Agent 清洗 + 四路匹配技术（不靠瞎总结）
1. **精准关键词直查**：SQLite `FTS5` trigram 倒排冷库（短词自动回退 `LIKE` 查精确原话）。
2. **向量语义相似度**：500 字滑窗 / 80 字重叠切块后编码（L2 归一化原空间 `rec_raw`），长对话尾段零截断（默认纯 Python 标准库即跑；可选 `--use-fastembed` 接入 `BAAI/bge-small-zh-v1.5`）。
3. **去均值余弦聚簇**：`L2(v - mu)` 消除语义偏心聚集（anisotropy），拆清过去把时间花在了哪些话题上。
4. **跨簇模式磁铁 + 防误报门禁**：回原空间全盘扫描重复踩坑，自动拦截**主宾反转**（“我没听懂” vs “你没理解我”）与**否定词钝感**（“先别做” vs “直接做”），按分层抽样导出带 `[REC-xxxx]` 原文编号的 `backfill_candidates.md` 供人核实回填。

### Stage 4：6 件套验收与跨端挂载
- 使用 [templates/](templates/) 中的 6 份空白模板（1 份 `AGENTS.md` + 5 份个人档案 `00~04`）定稿自己的手册，并用 `python -X utf8 scripts/03_validate_kit.py --target <目录> --strict` 检查是否还有未填占位符、空话或本地路径隐私泄露。

#### UNCERTAIN_PROSE：自然语言不确定性告警（issue #2 Bug C）

除字面 `[待确认]` 标记外，validator 还扫描口语化的存疑表达（记不清 / 记不得 / 记不住 / 待核实 / 未核实 / 说不准 / 不确定 / 可能记错 / 大概 / 印象里 / 好像 / 忘了细节 / 有待确认），命中输出 `文件:行号 命中词｜原文行`，并在结尾给出条数汇总。

- 该通道**默认只警告、不失败**；即使加 `--strict` 也不阻断（采集阶段允许存疑）。交付阶段若要求零存疑，加 `--fail-on-uncertain-prose` 可把告警升级为失败。
- 匹配前先做归一化（NFKC 全/半角折叠 + 去除空白），“待 核 实”“待　核　实”这类插空格/全角空格写法不会漏检。
- **已知局限**：否定语境（“不是不确定”“已核实，不存在不确定”）与复合词（“不确定度”）按窄规则豁免，但口语否定形态无法穷尽；残留误报可用 `--uncertain-prose-ignore <子串>` 按行豁免。规则引用句（如“严禁猜『大概 / 差不多』”）目前仍可能命中，属于待后续用引用例句豁免规则处理的边界。

---

## 三、安装预检与三分钟现场演示（流水线零第三方依赖，测试需 pytest）

### 3.0 普通用户零终端安装与预检

你不需要打开终端、不需要自己装 Python 或 clone 仓库——把这些交给本地 Agent 替你执行这两条命令：

```bash
python -X utf8 scripts/00_doctor.py       # 输出 DOCTOR_OK 即环境就绪（exit 0）
python -X utf8 scripts/99_smoke.py        # 输出 SMOKE_OK 即流水线可用（exit 0）
```

`00_doctor.py` 会**真实验证** Python ≥ 3.11、SQLite FTS5 + trigram 建表/插入/查询、工作目录可写、必需脚本与模板齐全；任一项不满足会给人话提示并以 exit 2 结束，不会把堆栈丢给你。可用 `--root 仓库目录` 指定仓库位置（省略时默认脚本所在仓库根目录）。

`99_smoke.py` 会在系统临时目录跑通 `01 → 02 → 03` 最小样例，不污染仓库 `work/`，输出 `SMOKE_OK` 即表示清洗、匹配、校验三段流水线都可用。

### 3.1 三分钟现场演示

**环境要求：Python 3.11+。** 清洗、匹配、校验脚本只使用标准库；只有最后的 `pytest` 测试需要单独安装开发依赖。

仓库自带一套完全虚构脱敏的示例数据 [examples/sample_raw/](examples/sample_raw/)，在根目录直接运行：

```bash
# 0. 安装测试依赖（仅第一次；不跑测试可跳过）
python -m pip install -r requirements-dev.txt

# 1. 清洗去重 + 建立 SQLite FTS5 冷库
python -X utf8 scripts/01_clean_and_index.py --raw examples/sample_raw --db work/unified_index.db --query 记错

# 2. 运行四路匹配 + 主宾/否定门禁过滤，产出人工回填清单
python -X utf8 scripts/02_four_way_match.py --db work/unified_index.db --out work/backfill_candidates.md

# 3. 校验空白模板结构（制作完自己的版本后加 --strict 检查是否留有未填占位符）
python -X utf8 scripts/03_validate_kit.py --target templates

# 4. 跑全套单元测试
python -m pytest -v
```

---

## 四、给其他 AI / Agent 使用本仓库的接入方式

- **仓库自带工程规范**：根目录已按 [AGENTS.md](AGENTS.md)、[GLOSSARY.md](GLOSSARY.md)、[docs/adr/](docs/adr/) 与 `.scratch/` 约定配齐。
- **任意本地 Agent 接管**：告诉它：“请读取仓库根目录的 `AGENTS.md` 与 `skills/onboarding-interviewer/SKILL.md`，带我跑完个人入职说明书建档、清洗并运行 `03_validate_kit.py` 验收。”
