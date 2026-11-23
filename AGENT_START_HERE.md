# AGENT_START_HERE · 给任何零环境 Agent 的入口

你只需要 Python 3.10+。核心路径没有第三方依赖；`pytest` 只在开发时用。

## 0. 先体检（10 秒）

```powershell
py -3.12 -X utf8 scripts/xh.py doctor
```

看到 `DOCTOR_OK` 再往下。`ERROR:` 必须解决；`WARN:` 可以先记录。

> 解压坑（issue #55）：Linux 老 `unzip`（Info-ZIP 6.00）会忽略 zip 的 UTF-8 标志，把中文模板名解成乱码，doctor 会报“文件名编码损坏（不是缺模板）”。这时不要重打包，改用 `python3 -m zipfile -e 发布包.zip 目标目录`，或用 `.tar.gz` 包 `tar -xzf` 重新解压；Windows 用右键“全部解压”或 `python -m zipfile -e`。

## 1. 初始化工作区

```powershell
py -3.12 -X utf8 scripts/xh.py init
```

会在 `work/` 建：

- `raw/`：只读原始导出，别让模型改写
- `interview/`：6 轮访谈原始回答
- `kit/`：6 份档案草稿
- `reports/`、`evidence/`

> **注意（不是安装失败）**：`init` 之后 `work/kit/` 是空白模板，里面的 `<...>` 占位符还没填。这时直接 `validate --strict` 会报占位符，属正常现象。下一步：把聊天记录放进 `work/raw/` 跑 `build`，或先做 S1 访谈，再校验。

## 2. 只有聊天记录，先出一版 6 份初稿（推荐）

如果手上已经有导出的 `work/raw/`，一条命令走完：

```powershell
py -3.12 -X utf8 scripts/xh.py build --raw work/raw --db work/unified_index.db --kit work/kit --l2 work/layer2
```

期望：

```text
INDEX_OK ... -> FOUR_WAY_OK ... -> BOOTSTRAP_OK ... -> L2_BACKFILL_OK candidates=N
-> TEMPORAL_BACKFILL ... -> GRAPH_BUILD ...
-> RECALL_OK temporal=N -> RECALL_OK graph=N -> RECALL_OK keyword=N
-> VALIDATE_OK -> BUILD_OK
```
`build` 默认会把三路检索也跑一遍；只要 `--skip-retrieval` 才跳过。三路都是辅助召回，不是 6 份档案的替代品。

产物：
- `work/kit/`：6 份首轮档案 + `_evidence/chat-lines.md`（每条都带行号原文）
- `work/kit_next/`：在首轮档案上追加“二层回流待确认区”的 6 份文件（机器候选，未签字）
- `work/layer2/l2_candidates.md`：二层回流候选（全部待确认，未签字不生效）
- `work/backfill_candidates.md`：一层四路匹配报告

`build` 默认还会跑 `08_l2_apply.py`，把二层候选以 `[待确认]` + `原文/出处` 的待确认区写进 `work/kit_next/`；这不是签字，也不是把候选当事实。只想保留首轮时加 `--no-l2-apply`。

这条命令只做**机器初稿**：`AGENTS.md` 会明确写 A/B/C 三级事实，`01`–`04` 的每条候选都带 `原文` + `出处`。它不替本人签字，也不把 assistant 的总结当用户记忆。

`BUILD_OK` 不等于“可以交付”。下一步必须做一次**接手 Agent 复核**：

1. 打开 `work/kit_next/_evidence/chat-lines.md`（或首轮 `work/kit/_evidence/chat-lines.md`），逐条核对 `01`–`04` 的引用；
2. 把“请求/提示词/assistant 总结”误入 B 级的条目删掉，只保留本人自述、规则、判断、正反例；
3. 对 `work/kit_next/` 的“二层回流待确认区”，逐条判断：本人亲历？AI 代做/转述？已讲过？值得升格？不值得就删；
4. 保留 `[待确认]`，不要用常识补全；本人签字后才可用 `backfill --apply-signed --confirm` 写入正式档案；
5. 改写后重跑 `validate --strict`，仍要 `VALIDATE_OK`；
6. 再把 `work/kit_next/` 交给下一个 Agent，而不是把机器初稿直接当定稿；
7. 复核通过后落回执：`py -3.12 -X utf8 scripts/xh.py review --confirm --kit work/kit`。
   build 回执与档案旁的 `_evidence/review.json` 初始状态都是 `pending_review`；
   没跑这一步，`verify` 与 S7 三问盲测会被阻断，并提示先复核，Agent 不能自行代签。

## 3. 真实全流程（推荐顺序）

```text
S0 doctor
S1 访谈 6 轮 → work/interview + work/kit
S2 浏览器导出 → work/raw
S3 ingest → work/unified_index.db
S4 match → work/backfill_candidates.md
S5 validate → work/kit
S6 二层 backfill → 需要本人逐条签字
S7 verify → 交付
```

每一步只做一步；做完给命令、退出码、关键输出、产物路径，再问“继续？”。

### S1 访谈

读 `skills/onboarding-interviewer/SKILL.md`，6 轮、每轮 3 题；不要替用户编答案。每轮把回答写进 `work/interview/round-N.md`，再生成 `work/kit/` 的 6 份草稿。

### S2 导出

优先看 `docs/02-multi-platform-export.md`：ScriptCat（引擎）+ AfterChat（工人），下载后用 `Ctrl+J` 核对落盘路径。

如果目标 Agent **没有浏览器扩展权限**，用浏览器工具直接读当前会话 DOM：

1. 打开已登录的对话页（豆包会话页等）；
2. 让浏览器 Agent 读取消息行（豆包是 `.v_list_row`；有 `send-msg-bubble` 的是 User，否则 Assistant）；
3. 按 AfterChat 兼容格式写 Markdown：

```markdown
## Metadata
- **Source:** <url>
- **Time:** YYYY-MM-DD

## Conversation

### 🧑‍💻 User

<原文>

### 🤖 Assistant

<原文>
```

4. 落盘到 `work/raw/`，再用 `01` 验证 `INDEX_OK`。

这条 DOM 兜底只适用于**你自己账号、自己可见**的会话；不要把别人的聊天或登录态抓下来。

### S3–S5 三条命令

```powershell
py -3.12 -X utf8 scripts/xh.py ingest --raw work/raw --db work/unified_index.db --query 记错
py -3.12 -X utf8 scripts/xh.py match --db work/unified_index.db --out work/backfill_candidates.md
py -3.12 -X utf8 scripts/xh.py validate --kit work/kit --strict
```

### S6 二层回流

只有 `scripts/05_deep_backfill.py` 存在时才可用：

```powershell
py -3.12 -X utf8 scripts/xh.py backfill --profiles work/kit --first-pass work/backfill_candidates.md --db work/unified_index.db --out work/layer2
```

`--apply-signed` 必须由本人对每条候选确认后再加；不要让 Agent 自己签字。

Agent 可以先把候选机械地落成“未签字待确认区”，给本人复核：

```powershell
py -3.12 -X utf8 scripts/xh.py l2-apply --kit work/kit --l2 work/layer2 --out work/kit_next
py -3.12 -X utf8 scripts/xh.py validate --kit work/kit_next --strict
```

`08_l2_apply.py` 只做三件事：复制 6 份档案、追加带 `[待确认]` + `原文/出处` 的待确认区、重跑严格校验。它不会填签字栏，也不会改正式档案。

### S6b 检索层（图 / 时间 / 关键词）

需要先有 `work/unified_index.db`（S3 产物）：

```powershell
py -3.12 -X utf8 scripts/xh.py retrieval --db work/unified_index.db --as-of 2026-11-20 --limit 50
```

它会依次跑 `05_temporal_index.py backfill`（事件时间优先、未知不伪装成提及日）、`06_graph_index.py build`（规则抽取实体-关系边；未知事件不伪造 valid time）、`07_recall_time_graph.py`（时间 / 1~2 跳图 / FTS 关键词三路召回）。这是**辅助检索**，不是 6 份档案的替代品；图的抽取是规则法，召回不保证覆盖开放域表达。

### S7 最终验收

```powershell
py -3.12 -X utf8 scripts/xh.py verify --kit work/kit --strict
```

看到 `VALIDATE_OK` 才算 6 文件结构合格。若档案还是 `pending_review`，`verify` 会先阻断并提示跑 `review --confirm`。再用一个**全新的** Agent 只读 `work/kit/AGENTS.md` 和 5 份档案，确认它能复述你的判断准则、红线和当前主线；不能，就回到 S1/S6。

## 4. 快速演示（不访谈、不导出）

```powershell
py -3.12 -X utf8 scripts/xh.py demo
```

期望 `INDEX_OK → FOUR_WAY_OK → VALIDATE_OK → DEMO_OK`。

## 5. 交付给下一个 Agent

把 `work/kit/` 整个目录给它可以；或者先打包：

```powershell
py -3.12 -X utf8 scripts/xh.py package --out dist/xh-dossier.zip
```

包里不含 `work/`、`.git/`、`dist/`；raw 和访谈原文默认只留本机。

## 6. 硬边界

- 不伪造访谈答案；不确定写 `[待确认]`，并给出原文/出处。
- 不把提及时间当事件时间；看 `said=` 和 `event=` 两列。
- 不把 assistant 的 Thought Process 当用户记忆。
- 不替用户签字；`--apply-signed` 只能本人确认后执行。
- 不把别人的聊天、Cookie、密码、验证码写进 raw。
- 浏览器 `Save As` 原生弹窗、登录/验证码必须交还本人。
