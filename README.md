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
- **本地 Agent 用户**：加载 [skills/onboarding-interviewer/SKILL.md](skills/onboarding-interviewer/SKILL.md)，按 **6 个阶段**推进；每个阶段先问 2–3 个种子问题，拿到该阶段目标才进下一阶段（6 个阶段分别对应 `AGENTS.md` + `00~04` 六份文件）。
- **网页端用户**：复制 [prompts/01_web_ai_interviewer.md](prompts/01_web_ai_interviewer.md) 里的完整提示词直接发给豆包 / DeepSeek / GLM。

### Stage 2：多平台聊天记录导出（内置 ScriptCat 脚本猫向导 + 开关避坑）
详见 [docs/02-multi-platform-export.md](docs/02-multi-platform-export.md)，或先运行仓库内置的同意门禁引导脚本 `python -X utf8 scripts/00_export_wizard.py --browser edge` 获取开源扩展 **ScriptCat（脚本猫）** 官方安装入口。
**⚠️ 装扩展只是装了「引擎」，还必须装一个「导出脚本」才干活**：多平台推荐 **AfterChat**（GreasyFork #589622，约 30 平台），单平台备选见指南里的「按平台选脚本」表。另一个高频坑是浏览器的「下载前询问保存位置」——导出跑完会弹系统「另存为」窗口，需本人点保存，否则进度看似卡住、文件不落地。
**网络退路**：浏览器商店、scriptcat.org 或 GreasyFork 打不开 / 超时时，引擎 ScriptCat 可直连 GitHub 开源发布页下载压缩包（向导加 `--download-release`）；按平台与场景的主路径 / 备选路径见指南「网络场景退路」一节。
**⚠️ 浏览器开关最容易卡住的一步**：
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

---

## 三、安装预检与三分钟现场演示（流水线零第三方依赖，测试需 pytest）

### 3.0 普通用户零终端安装与预检

> **目录要求**：下面所有命令都先 `cd` 到仓库根目录再运行。在别的目录用相对路径调 `scripts\xh.py` / `00_doctor.py` 会报 `can't open file ... [Errno 2] No such file or directory`——这不是脚本坏了，而是当前目录不是仓库根；先 `cd` 到仓库根，或用脚本绝对路径调用。

你不需要打开终端、不需要自己装 Python 或 clone 仓库——把这些交给本地 Agent 替你执行这两条命令：

```bash
python -X utf8 scripts/00_doctor.py       # 输出 DOCTOR_OK 即环境就绪（exit 0）
python -X utf8 scripts/99_smoke.py        # 输出 SMOKE_OK 即流水线可用（exit 0）
```

`00_doctor.py` 会**真实验证** Python ≥ 3.11、SQLite FTS5 + trigram 建表/插入/查询、工作目录可写、必需脚本与模板齐全；任一项不满足会给人话提示并以 exit 2 结束，不会把堆栈丢给你。可用 `--root 仓库目录` 指定仓库位置（省略时默认脚本所在仓库根目录）；`scripts/xh.py doctor` 提供同样的 `--root` 参数。

#### Windows 一键安装（可选）

在仓库根目录运行：`powershell -ExecutionPolicy Bypass -File install.ps1`。默认安装到 `%USERPROFILE%\XH-Dossier`；已有目录会覆盖同名文件，想显式覆盖可加 `-Force`。

#### 机器上没有 Python 怎么办（最低版本 3.11）

本系统核心路径只依赖 Python 标准库，但仍需要一个 **Python 3.11 或更新版本** 的解释器。检测不到时，`install.ps1` 会自动下载官方 **Python 3.12.10 embeddable zip** 到 `%LOCALAPPDATA%\XH-Dossier\python`，写入 `python312._pth` 并做 sqlite3 自检；日志里会出现 `DOWNLOAD_OK`、`EXTRACT_OK`、`PTH_OK`、`BOOTSTRAP_OK`。不需要先手工装 Python，也不需要 `py` launcher。

如果机器已有 Python 3.11+，安装器会直接使用它；`-ForceBootstrap` 只用于强制走 bootstrap 分支做验收，不应作为普通安装的默认参数。

只有企业网络/代理阻断 `python.org`、下载失败时，才需要按报错里的入口手工安装后重跑：

- **winget（Windows 自带包管理器，一条命令）**：`winget install Python.Python.3.12`
- **官网下载页**：https://www.python.org/downloads/  选 Python 3.11 或更新版本；安装第一屏勾选 **Add python.exe to PATH**，再点 Install。
- 装好后重开终端，`python --version` 能打印版本号即就绪。

#### 共享机器 / per-user 安装被 launcher 拦截时的退路

如果装 Python 时报「Product ... is admin assigned / 系统策略禁止这个安装」（安装错误 1625），通常是 **py launcher 已被管理员分配**，per-user 安装被拦截。Python 本体仍可绕过 launcher 装上：

- 官网安装包选 **Install for current user（仅当前用户）**，自定义安装参数加 `Include_launcher=0`（不装 py launcher）；
- 或 winget：`winget install Python.Python.3.12 --scope user --override "Include_launcher=0 InstallAllUsers=0 PrependPath=1 Include_test=0"`；
- 这种机器上后续命令一律用 `python` 调用，不要用 `py -3.x`。

### 3.0.1 `init` 之后 `work/kit` 是空白模板，`--strict` 报错属正常

`init` 只会把 6 份空白模板复制到 `work/kit/`，里面的 `<...>` 占位符还没填。这时直接跑 `validate --strict` 会报占位符，**这不是安装失败**。下一步：把聊天记录放进 `work/raw/` 后跑 `build`，或先完成 6 个阶段访谈，再做严格校验。

`99_smoke.py` 会在系统临时目录跑通 `01 → 02 → 03` 最小样例，不污染仓库 `work/`，输出 `SMOKE_OK` 即表示清洗、匹配、校验三段流水线都可用。

#### 解压后中文文件名乱码怎么办（Linux / Agent 常见坑，issue #55）

发布 zip 里的中文模板文件名**已经带 UTF-8 标志**，但 **Info-ZIP UnZip 6.00（2009）这类老解压器会忽略这个标志**，按本地代码页解释字节，解出来变成 `00-цА╗...`、`00-µÇ╗...` 或一串代理字节；重新打包、再打一次 UTF-8 标志修不好，问题在解压端，不在打包端。

- **Linux 主路径**：不要直接用 `unzip` 解含中文文件名的 zip，用 Python 标准库：

  ```bash
  python3 -m zipfile -e 发布包.zip 目标目录
  ```

  或下载 `.tar.gz` 包后：`tar -xzf 发布包.tar.gz -C 目标目录`。
- **Windows 主路径**：资源管理器右键“全部解压”（Expand-Archive / .NET），或 `python -m zipfile -e 发布包.zip 目标目录`。
- **退路**：`bsdtar -xf 发布包.zip`（libarchive，认 UTF-8）。`unzip -O UTF-8` 只是 Debian/Ubuntu 的本地补丁，不是上游标准，部分发行版没有这个选项，不能当主路径。

`doctor` 会把两类问题分开报：**“文件名编码损坏（文件其实在，不是缺模板）”** 表示文件在、只是名字乱码，按上面命令重新解压即可；**“缺少必需文件”** 才是仓库真的不完整。

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
