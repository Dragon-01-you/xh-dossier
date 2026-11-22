# Changelog

本文件只记录**真实合并、真实跑通**的变更。未验证的计划不写进来。

## 0.2.0-rc.4 — 2026-11-23

### 收紧机器初稿噪声（真实 729 复跑）
- `04_bootstrap_kit.py`：候选句跳过列表编号、对话式排障（“你等一下/你这里/怎么回事”）；反例只保留强负面结果，不再把“问题”二字当反例。
- `05_deep_backfill.py --broad`：判断/反例 cue 去掉“先/再/核心/关键”“问题/坑”等过宽词；broad 候选必须落到一句 20–220 字的原话，并跳过请求/命令句。
- 真实 59 导出 / 729 条：`identity=4 mainline=3 principles=0 rules=8 negative=2 positive=4`；二层 broad 候选从 35 降到 1，且该条是真实身份自述（3D 可视化项目），不是请求或歌词。
- 最新代码完整三路复跑：`TEMPORAL_BACKFILL 729 / unknown=692`、`GRAPH_BUILD edges=1149`、三路分别 `temporal=5 / graph=5 / keyword=5`、`VALIDATE_OK`、`BUILD_OK`。

### 说明
- `principles=0` 是诚实留空：规则法找不到“本人判断准则”的完整声明句，不拿提示词凑数；`04` 的正例/反例仍可读。
- `BUILD_OK` 仍不等于可交付；接手 Agent 必须按 `AGENT_START_HERE.md` 做逐条复核。

## 0.2.0-rc.3 — 2026-11-23

### 新增：从混乱聊天直接生成 6 份初稿
- `scripts/04_bootstrap_kit.py`：从 SQLite 真实用户消息生成 `AGENTS.md` + 5 份档案 + `_evidence/chat-lines.md` 行号证据。
- 每条候选带 `原文` + `出处`；不确定项用合规 `[待确认]`（原文/出处齐全），不放宽 `--strict`。
- 生成前清理本地路径、手机号、证件号、`SecretId` / `SecretKey` / `AKID`；提示词模板、assistant 文本、辱骂/歌词类噪声不进入档案。
- 优先使用工作类会话标题（项目/知识库/AI/3D/设计等）；工作样本不足时才回退全量。
- 真实 59 个豆包导出、729 条记录：108 条可用工作原话 → 6 份档案 `VALIDATE_OK`；真实 DOM 兜底 5 个会话 → 18 条记录 → `BUILD_OK`。

### 新增：一条命令跑完主链路
- `scripts/xh.py build`：`raw → 01 index → 02 match → 04 bootstrap → 05 broad backfill → 05/06 index → 07 三路召回 → 03 validate` 一条命令；默认跑检索，`--skip-retrieval` 才跳过。
- `scripts/xh.py bootstrap`：只生成 6 份初稿。
- `05_deep_backfill.py --broad`（`xh.py backfill --broad`）：在严格自挫信号之外，补充未被档案引用的身份/规则/判断类原话；每条仍 `needs_llm=true` 且未签字。
- `08_l2_apply.py`（`xh.py l2-apply`）：把二层候选复制成 `kit_next`，追加“二层回流待确认区”，每条带 `原文/出处`；不填签字栏，不改正式档案。`build` 默认调用它，`--no-l2-apply` 可关闭。
- `04_bootstrap_kit.py` 增加请求句/粘贴材料/表格式清单过滤，候选只保留本人自述的完整句子；真实 59 导出从“请求混入身份”降到 `identity=4 / mainline=3 / principles=1 / rules=8 / negative=8 / positive=0`（正例样本不足时明确留空，不硬凑）。

### 修复：密钥泄漏
- `03_validate_kit.py` 的敏感信息正则新增 `AKID...` 与 `SecretId/SecretKey/AccessKey...`；生成器和校验器双层拦截。

### 测试
- 新增 `tests/test_bootstrap_kit.py`：6 份文件严格校验、证据行、密钥不泄漏、broad 只产未引用原话、二层未签字区可校验。
- 全量 `192 passed`；真实 6 档案 `VALIDATE_OK`；真实 59 导出 `BUILD_OK`；真实 729 库三路召回分别命中 `temporal=5 / graph=5 / keyword=5`。

## 0.2.0-rc.2 — 2026-11-23

这是 main 合并后的发布候选，尚未打 tag、尚未生成 GitHub Release。

### 新增：给零环境 Agent 的一键入口
- `install.ps1`：Windows 一键安装到指定目录，自动检测 Python 3.10+，跑 `doctor` / `init`，可选 `demo`；源目录与目标目录相同时只跑体检，不复制。
- `scripts/xh.py`：统一 CLI，封装 `doctor / init / demo / ingest / match / retrieval / backfill / validate / verify / package / status`。
- `scripts/xh.py retrieval`：一条命令跑 `05_temporal_index.py backfill` → `06_graph_index.py build` → `07_recall_time_graph.py`，把时间、1~2 跳图、FTS 关键词三路召回串起来。
- `AGENT_START_HERE.md`：任意 Agent 先读这一页；含无扩展权限时的 DOM 导出兜底格式与落盘验证。
- `templates/`、`skills/onboarding-interviewer/` 随仓库分发。

### 修复：真实 6 档案命名兼容
- `03_validate_kit.py` 接受真实命名 `04-反面案例清单.md`（别名到 `04-正反例避坑账.md`），不再把真实档案误判为缺文件。
- 运行期变量 `<任务>` / `<项目>` / `<日期>` / `<分支>` 不再被当作未填占位符；模板里的 `<填写...>` 仍会在 `--strict` 下失败。
- 真实 6 档案 `E:\芯火知识库\芯火知识库\个人知识库\00-热加载核心` 已实测 `VALIDATE_OK`。

### 修复：事件时间与提及时间分离（#10 / #37 / #46 / #49）
- `event_time.py`：普通陈述/状态句不再复制 `created_at`；`目前/现在的目录` 不当作“当天事件”；显式过去日期即使没有“记得/以前”也判 retrospective；assistant 一律 `event_date=""`。
- `05_temporal_index.py`：导出存在 `event_date` 列时，空值/不可解析值一律 `valid_from=""`，未知事件时间不伪装成提及日；事务时间仍用 `created_at`。
- `06_graph_index.py`：图边同样不伪造事件时间；实体名按 `(-len(name), name)` 排序，四次不同 `PYTHONHASHSEED` 重建边数稳定为 1149。
- 真实 59 个豆包导出、729 条记录重建：`assistant unknown=383 / user retrospective=32 / user stated=34 / user unknown=280`；`REC-0018` 角色提示为 `event="" / unknown`；四路匹配 `FOUR_WAY_OK records=729 clusters=54`；`GRAPH_BUILD entities=2945 edges=1149 negation_skipped=25`。

### 修复：缺 DB 人话错误（#13 / #38）
- `02_four_way_match.py` 捕获 `FileNotFoundError`，输出 `DB_NOT_FOUND` + 下一步，exit 2，不建空库、不写空报告。
- 补 `PERMISSION_DENIED`（DB 锁定/只读）人话错误，exit 2。

### 修复：校验器边界（#2 / #15 / #39）
- cliché 绕过：整行出现“禁止/严禁/不要说”不再无条件豁免；引号内合法引用仍豁免，引号后带动词仍失败。
- 硬失败不存在的日期（`2025-02-30`、`2025-13-01`），闰年 `2024-02-29` 与月级 `2025-02` 保持合法。
- `[待确认]` tri-state：合规三要素/裸标记/纯元引用分别处理；`--strict` 下裸标记失败。
- 自然语言不确定（记不清/记不得/记混/待核实/说不准/拿不准/没印象/想不起来 等，含 NFKC+去空白后的“待 核 实”）直接 `UNCERTAIN_SEMANTIC` 硬失败，不再需要字面 `[待确认]` 才拦。
- 出处校验升级为文件/行号/引文三件套：引用必须落在 kit 目录或显式 `--source-root` 内；拒绝 `..`、盘符、绝对路径穿越。

### 修复：二层回流（#6 / #35 / #42）
- `05_deep_backfill.py` 路径穿越防护；候选必须带本人签字才 `--apply-signed`。
- 真实 729 库上 `personal_records=346 / candidates=0 / cross_ref_L1=0`；`dropped_by_reason` 主因 `no_self_setback_signal`、`non_personal`；这是规则法在真实语料上的已知限制，不声称已证明增量价值。

### 文档：访谈、导出与检索设计
- `docs/01-onboarding-interview.md`：6 轮访谈加入深钩追问、语言跟随、Q3 拆分、每轮末尾开放位。
- `docs/02-multi-platform-export.md`：ScriptCat（引擎）与 AfterChat（工人）分层、平台决策表、单对话 `.md` vs 列表 `.zip`、另存为/`Ctrl+J` 人工确认门；补充真实 DOM 兜底导出（4 条消息实测 `INDEX_OK total_raw=4 indexed=4`）。
- `docs/design-retrieval-layer3-4.md` 与 `docs/03-retrieval-layer3-4-graph-temporal.md`：检索③④设计任务书（图/时间检索范围、表结构、召回路径、验收口径）。

### 测试与验收
- main：`187 passed`；release2：`189 passed`。
- 真实 6 档案 strict：`VALIDATE_OK`。
- 全新目录一键安装：`INSTALL_OK` + `DEMO_OK`（`INDEX_OK → FOUR_WAY_OK → VALIDATE_OK`）。
- `xh.py retrieval` 在 demo 库上真实跑通：`05 backfill` → `06 build` → `07 recall`，exit 0。

### 仍未闭环（不得写成已完成）
- 真实 AfterChat「登录态 → 白色导出按钮 → 另存为 → Ctrl+J 核对落盘」仍需用户本人在场；DOM 兜底只验证了 4 条消息。
- 真实 6 轮访谈 + 新 Agent 从混乱聊天生成 6 份档案，仍需用户本人参与验收；现有真实 6 档案是用户既有档案，不是本轮新访谈产物。
- PR #35 二层回流在真实 729 库上候选为 0；是否保留该能力需用户裁决。
- `#5` 的图/时间检索是规则法实现，开放域召回质量未做人工标注评估。
- 发布门禁：`dist/xh-dossier.zip`、tag、GitHub Release 尚未生成；需用户批准。
