# AGENT_START_HERE · 给任何零环境 Agent 的入口

你只需要 Python 3.11+。核心路径没有第三方依赖；`pytest` 只在开发时用。

> **目录要求**：下面所有命令先 `cd` 到仓库根目录再运行；在别的目录用相对路径调脚本会报 `can't open file ... [Errno 2] No such file or directory`，先检查当前目录是不是仓库根。机器上没有 Python 时的安装入口、共享机器 per-user（被 launcher 拦截）退路，见 README「3.0 普通用户零终端安装与预检」。

> 解释器说明：命令里的 `python` 指当前可用解释器；有 py launcher 的 Windows 也可用 `py -3.x`（x 为已装的次版本号）。

## 0. 先体检（10 秒）

```powershell
python -X utf8 scripts/xh.py doctor
```

看到 `DOCTOR_OK` 再往下。`ERROR:` 必须解决；`WARN:` 可以先记录。

> 解压坑（issue #55）：Linux 老 `unzip`（Info-ZIP 6.00）会忽略 zip 的 UTF-8 标志，把中文模板名解成乱码，doctor 会报“文件名编码损坏（不是缺模板）”。这时不要重打包，改用 `python3 -m zipfile -e 发布包.zip 目标目录`，或用 `.tar.gz` 包 `tar -xzf` 重新解压；Windows 用右键“全部解压”或 `python -m zipfile -e`。

## 1. 初始化工作区

```powershell
python -X utf8 scripts/xh.py init
```

会在 `work/` 建：

- `raw/`：只读原始导出，别让模型改写
- `interview/`：6 个阶段访谈原始回答
- `kit/`：6 份档案草稿
- `reports/`、`evidence/`

> **注意（不是安装失败）**：`init` 之后 `work/kit/` 是空白模板，里面的 `<...>` 占位符还没填。这时直接 `validate --strict` 会报占位符，属正常现象。下一步：把聊天记录放进 `work/raw/` 跑 `build`，或先做 S1 访谈，再校验。

## 2. 只有聊天记录，先出一版 6 份初稿（推荐）

如果手上已经有导出的 `work/raw/`，一条命令走完：

```powershell
python -X utf8 scripts/xh.py build --raw work/raw --db work/unified_index.db --kit work/kit --l2 work/layer2
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
7. 复核通过后落回执：`python -X utf8 scripts/xh.py review --confirm --kit work/kit`。
   build 回执与档案旁的 `_evidence/review.json` 初始状态都是 `pending_review`；
   没跑这一步，`verify` 与 S7 三问盲测会被阻断，并提示先复核，Agent 不能自行代签。

## 2.5 每步流程意图与允许兜底边界

接手 Agent 不要机械盲跑命令；执行前先看清每一步的**设计目标**、**允许的轻量兜底范围**，以及**何时必须停手问人**：

| 阶段 | 设计目标 | 预期产物 | 允许 Agent 兜底的微小偏差 | 必须停手问人的红线 |
|---|---|---|---|---|
| 1. 冷库入库（`ingest`） | 只读吸收多平台导出并去重、建 FTS5 索引 | `unified_index.db`（`INDEX_OK`） | 压缩包需先解压到系统临时目录再传 `--raw`；解释器按 `py`/`python`/`python3` 自动切换 | 原始导出目录为空、下载中断或疑似混入他人聊天记录 |
| 2. L1 访谈校准与初稿（`bootstrap`） | 把本人确认的访谈立为 A 级基准，再从聊天抽 B 级补证 | 6 份初稿 + `_evidence/` + `build_summary.md` | 访谈为预填卡或 `answers.md`/`stage-N.md` 均可自动吸收；raw 样本薄时诚实保留“需访谈” | 显式传入访谈却报 `INTERVIEW_WARN` 解析为 0 条；或访谈与 raw 冲突需本人裁决 |
| 3. L2 差集挖掘（`backfill`） | 找出 6 份档案尚未覆盖的本人遗漏经验与复盘 | `layer2/l2_candidates.md` + 待确认补丁区 | 可开 `--broad` 扩大未覆盖陈述召回；所有结果仅放未签字待确认区 | 任何涉及 `--apply-signed --confirm` 改写正式正文的操作（严禁代签） |
| 4. 时间线与图检索（`retrieval`） | 提供双时态与实体关系辅助查账，不替代 6 份档案 | `entities`/`relations` 表 + 召回清单 | 缺失日期保留 `unknown` 不猜；可选 `--skip-retrieval` 先看 L1/L2 质量 | 把 `assistant` 独白或未经 `rec_id + quote` 验真的推断塞进正式档案 |
| 5. 严格验收与复核（`validate` / `review`） | 验证出处存在、无水话/PII/空占位符并输出阶段转化摘要 | `VALIDATE_OK` + `PIPELINE_SUMMARY` | 先读 `build_summary.md` 确认每步“输入 → 过滤 → 产出”是否合理，再清理误入草稿 | `RAW_ZERO_HIT`、无法解释的缺失出处，或 `review --confirm` 本人签字动作 |

## 3. 真实全流程（推荐顺序）

```text
S0 doctor
S1 访谈 6 个阶段 → work/interview + work/kit
S2 浏览器导出 → work/raw
S3 ingest → work/unified_index.db
S4 match → work/backfill_candidates.md
S5 validate → work/kit
S6 二层 backfill → 需要本人逐条签字
S7 verify → 交付
```

每一步只做一步；做完给命令、退出码、关键输出、产物路径，再问“继续？”。

### S1 访谈

读 `skills/onboarding-interviewer/SKILL.md`，按 6 个阶段推进；每个阶段先问 2–3 个种子问题，拿到该阶段目标才进下一阶段，不按固定 3 题硬切。不要替用户编答案。每阶段把回答写进 `work/interview/stage-N.md`（兼容旧 `round-N.md`），再生成 `work/kit/` 的 6 份草稿。

### S2 导出

优先读 `prompts/02_dom_export_agent.md`，执行零扩展 DOM 导出：

1. 在本人已登录的浏览器打开目标会话页（不要用桌面客户端的内嵌浏览器）；
2. 确认 `.v_list_row`、`[data-message-role]`、`[data-testid="message_text_content"]` 仍在；
3. 执行 `scripts/dom_export.js`：有页面求值能力就直接执行；没有就粘贴到 DevTools Console；
4. 默认触发浏览器原生下载；也可以设 `window.__XH_DOM_EXPORT_NO_DOWNLOAD__ = true` 后读 `window.__XH_DOM_EXPORT__.markdown`，由 Agent 写进 `work/raw-doubao-dom/`；
5. 用 `python -X utf8 scripts/xh.py ingest --raw work/raw-doubao-dom --db work/unified_index.db --query 口播` 验证 `INDEX_OK`。

这条路径只导出**你自己账号、自己可见**的会话；不要把别人的聊天、Cookie、密码、验证码写进 raw。`scripts/dom_export.js` 以当前豆包 DOM 的 `[data-message-role]` 为角色依据，旧文档里的 `.send-msg-bubble` 已不是当前站点的可靠标记，不要用旧选择器硬猜。

如果必须用 AfterChat 扩展：先 `python -X utf8 scripts/xh.py export-setup --browser edge` 打开官方安装页；扩展安装的最终确认、浏览器原生「另存为」弹窗，仍由本人完成。

**发布口径（2026-11-24 起）**：DOM 导出只用于内部开发/临时救急；**对外发布必须走浏览器扩展 + AfterChat**。缺脚本管理器、缺 AfterChat、没登录态、下载目录不可写，一律停止并给出 [docs/00-install-one-click.md](docs/00-install-one-click.md) 里的直达链接，不要继续跑，也不要自建接收后台。

先跑环境检查，`ENV_OK` 才继续；缺件时退出码 1：

```powershell
python -X utf8 scripts/00_env_check.py --browser edge --dry-run
python -X utf8 scripts/10_export_gate.py --raw work/raw/afterchat --download-dir "D:\eage下载"
```

`10_export_gate.py` 没看到真实 `.md`/`.zip` 就返回 `EXPORT_BUTTON_MISSING` 或 `DOWNLOAD_INTERRUPTED`，退出码 1；此时停，不跑 S3。下载收尾崩溃时用 `11_finalize_download.py` 生成 `.md` 副本，不要猜“已经导出成功”。


### S3–S5 三条命令

```powershell
python -X utf8 scripts/xh.py ingest --raw work/raw --db work/unified_index.db --query 记错
python -X utf8 scripts/xh.py match --db work/unified_index.db --out work/backfill_candidates.md
python -X utf8 scripts/xh.py validate --kit work/kit --strict
```

### S6 二层回流

只有 `scripts/05_deep_backfill.py` 存在时才可用：

```powershell
python -X utf8 scripts/xh.py backfill --profiles work/kit --first-pass work/backfill_candidates.md --db work/unified_index.db --out work/layer2
```

`--apply-signed` 必须由本人对每条候选确认后再加；不要让 Agent 自己签字。

Agent 可以先把候选机械地落成“未签字待确认区”，给本人复核：

```powershell
python -X utf8 scripts/xh.py l2-apply --kit work/kit --l2 work/layer2 --out work/kit_next
python -X utf8 scripts/xh.py validate --kit work/kit_next --strict
```

`08_l2_apply.py` 只做三件事：复制 6 份档案、追加带 `[待确认]` + `原文/出处` 的待确认区、重跑严格校验。它不会填签字栏，也不会改正式档案。

### S6b 检索层（图 / 时间 / 关键词）

需要先有 `work/unified_index.db`（S3 产物）：

```powershell
python -X utf8 scripts/xh.py retrieval --db work/unified_index.db --as-of 2026-11-20 --limit 50
```

它会依次跑 `05_temporal_index.py backfill`（事件时间优先、未知不伪装成提及日）、`06_graph_index.py build`（规则抽取实体-关系边；未知事件不伪造 valid time）、`07_recall_time_graph.py`（时间 / 1~2 跳图 / FTS 关键词三路召回）。这是**辅助检索**，不是 6 份档案的替代品；图的抽取是规则法，召回不保证覆盖开放域表达。

### S7 最终验收

```powershell
python -X utf8 scripts/xh.py verify --kit work/kit --strict
```

看到 `VALIDATE_OK` 才算 6 文件结构合格。若档案还是 `pending_review`，`verify` 会先阻断并提示跑 `review --confirm`。
盲测包由 `python -X utf8 scripts/xh.py blind --kit work/kit --out work/blind` 生成，只拷六份档案、不带原始聊天 / 访谈 / 数据库；再用一个**全新的** Agent 隔离会话作答 `盲测三问.md`，用 `--score 作答表` 出三问 PASS/FAIL；不能复述判断准则、红线和当前主线，就回到 S1/S6。

## 4. 快速演示（合成样例，不读你的真实数据）

```powershell
python -X utf8 scripts/xh.py demo
```

它会用 `examples/sample_raw` + `examples/sample_interview`（**合成样例，不是真人访谈**）跑完整的
index → four-way → 6 份档案 → L2 待确认区 → 三路召回 → 严格校验。

期望 `INDEX_OK → FOUR_WAY_OK → BUILD_OK → SCORECARD_OK → VALIDATE_OK → DEMO_OK`。
如果看到 `SCORECARD_FAIL`，说明样例或校验门禁坏了，不要直接交付。

## 5. 交付给下一个 Agent

把 `work/kit/` 整个目录给它可以；或者先打包：

```powershell
python -X utf8 scripts/xh.py package --out dist/xh-dossier.zip
```

包里不含 `work/`、`.git/`、`dist/`；raw 和访谈原文默认只留本机。

## 6. 硬边界

- 不伪造访谈答案；不确定写 `[待确认]`，并给出原文/出处。
- 不把提及时间当事件时间；看 `said=` 和 `event=` 两列。
- 不把 assistant 的 Thought Process 当用户记忆。
- 不替用户签字；`--apply-signed` 只能本人确认后执行。
- 不把别人的聊天、Cookie、密码、验证码写进 raw。
- 浏览器 `Save As` 原生弹窗、登录/验证码必须交还本人。
