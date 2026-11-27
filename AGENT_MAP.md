# AGENT_MAP · 项目地图（Agent 先读这一页）

> 这是给任何接手 Agent 的“项目地图”。它回答四个问题：**这是什么、现在走到哪、下一步敲什么、卡住往哪跳。**
> 读完本页，再读 [AGENT_START_HERE.md](AGENT_START_HERE.md) 的细节；两页冲突时，以本页的阶段/门禁为准，以 START_HERE 的命令细节为准。

## 0. 核心优先（2026-11-25 用户定，先看这条）

只保两个核心，其他标准能砍就砍：

1. **回流并产出核心文件**：访谈 6 阶段是种子；第一次回流用**精确 + 相似**检索验证访谈、扩成 6 份；第二次回流用图 + 时间线补缺口、找冲突；两次都先回 6 份，放不进的回知识库候选。
2. **访谈 / 浏览器导出**：访谈 6 阶段先于浏览器配置（先知道有哪些平台），导出已经做过，视为默认步骤；Agent 主动提醒本人“该导哪台机器、哪个平台”，不重复要求本人从头做。

顺序固定：**访谈（先拿到平台清单）→ 浏览器/导出（默认已做）→ 第一次回流（精确/相似验证访谈，扩到 6×8 核心文件）→ 第二次回流（图检索 + 时间线，补缺口/冲突，签字回写）→ 回流去向（先 6 份，放不进的进知识库候选）→ 加固回流（后期靠项目反思，把重复错误变成检查/模板/门禁）**。环境准备是后期的第二模式，不塞进当前这次回流。

任何新增功能、适配、美化、平台扩展，先过一句：**它是否直接提升“上下文 → 带证据记忆 → 核心文件”？** 不能，就放后期候选，不维护。范围开始膨胀时，接手 Agent 要主动提醒用户回到这条。

技术合同见 [docs/core-reflow.md](docs/core-reflow.md)。

## 1. 一句话

**XH-Dossier 把散落在几十个聊天窗口里的“我说过的话”，收敛成 6 份带证据、可迁移、能被人签字的个人判断档案。**

它不是聊天记录摘要器，也不是自动替你写人设的 AI。它只做三件事：

1. 把原始聊天导出成**只读原件**（`work/raw/`）；
2. 从原件里找“本人自述、规则、判断、正反例”，做成**带原文/出处的候选**；
3. 候选必须经**本人复核/签字**，才允许写进正式档案。

一句话验收：**换一个没有上下文的 Agent，只给它 6 份档案，它能不能答对你当前的主线、判断准则和硬规则。**

## 2. 七段地图（S0–S7）

| 段 | 你要做什么 | 入口 | 产物 | 成功信号 | 失败往哪跳 |
|---|---|---|---|---|---|
| S0 体检 | 确认 Python、SQLite FTS5、目录可写、模板齐全 | `python -X utf8 scripts/xh.py doctor` | 终端回执 | `DOCTOR_OK` | 缺 Python → README 3.0；文件名乱码 → `python -m zipfile -e` |
| S1 访谈 | 6 个阶段问本人，不替本人编答案 | `skills/onboarding-interviewer/SKILL.md` + `work/interview/stage-N.md` | 访谈原文 + 6 份草稿 | `BOOTSTRAP_OK ... interview>0` | 没有访谈 → 先跑 S1；只有 raw → 可先出薄初稿，但不算完成 |
| S2 导出 | 把本人可见的会话导出成 `.md`/`.zip` | 本人点 AfterChat；或 `scripts/dom_export.js` 零扩展兜底 | `work/raw/` | `EXPORT_OK files=N` | 目录不存在 → `EXPORT_DIR_MISSING`；有 `.crdownload` → `11_finalize_download.py` |
| S3 清洗 | 原件 → SQLite 冷库；不改写原文 | `python -X utf8 scripts/xh.py ingest --raw work/raw --db work/unified_index.db --query 记错` | `unified_index.db` | `INDEX_OK(N)` | 0 条 → 检查导出格式/编码；不要手写假记录 |
| S4 匹配 | 查询词从访谈来，关键词/向量/实体/事件多路找候选（精确优先，相似只召回） | `python -X utf8 scripts/xh.py match --db work/unified_index.db --out work/backfill_candidates.md` | 一层候选报告 | `FOUR_WAY_OK` | 候选为空 → 放宽查询词/补导出；不要拿空报告当“没有事实” |
| S5 六件套 | 生成/校验 6 份档案草稿 | `python -X utf8 scripts/xh.py build --raw work/raw --db work/unified_index.db --kit work/kit --l2 work/layer2` | `work/kit/` + `work/kit_next/` | `VALIDATE_OK` | `VALIDATE_FAIL` → 按报错补槽位/删假引用；`SCORECARD_FAIL` → 看 `docs/scorecard.md` |
| S6 二次回流 | 在已有 6 份上接图 + 时间线，补缺口/找冲突；能回 6 份就回，回不去进知识库候选；逐条签字 | `python -X utf8 scripts/xh.py backfill --profiles work/kit --first-pass work/backfill_candidates.md --db work/unified_index.db --out work/layer2` | `work/layer2/` 候选 + `l2_review.jsonl` + `knowledge_candidates.md` | `L2_BACKFILL_OK`；签字后 `APPLY_SIGNED applied=N` | 签名被拒 → `SIGNING_KEY_MISSING` / `SIGNATURE_INVALID`；先 `--init-signing-key`，不要手改 ledger |
| S7 验收 | 本人复核 + 独立 Agent 盲测 + 交付 | `python -X utf8 scripts/xh.py review --confirm --kit work/kit` → `verify --strict` → `blind` | `review.json` + 盲测三问结果 + `dist/xh-dossier.zip` | `VALIDATE_OK` → `VERIFY_OK` → `BLIND_PASS` | 盲测失败 → 回 S1/S6 补事实；不能靠改答案表过关 |

## 3. 目录地图

```text
repo/
├── AGENT_MAP.md              ← 本页：项目地图 / 卡点分流
├── AGENT_START_HERE.md       ← 零环境 Agent 的详细操作手册
├── AGENTS.md                 ← 给“接手 AI”的合作站位与硬边界（只读）
├── README.md                 ← 人看的安装、四步流水线、导出说明
├── scripts/
│   ├── xh.py                 ← 唯一推荐入口（doctor/init/build/ingest/match/validate/backfill/verify/blind/...）
│   ├── 00_doctor.py          ← 环境体检
│   ├── 01_clean_and_index.py ← S3：清洗 + SQLite 索引
│   ├── 02_four_way_match.py  ← S4：多路匹配，只出报告，不回写
│   ├── 03_validate_kit.py    ← S5/S7：6 份档案结构/证据/评分卡校验
│   ├── 04_bootstrap_kit.py   ← S5：候选 → 6 份草稿
│   ├── 05_deep_backfill.py   ← S6：二次回流候选 + 签字台账 + 签名写回
│   ├── 05b_l2_theme.py       ← 主题聚类辅助（不碰时间）
│   ├── 08_l2_apply.py        ← 把待确认区写进 kit_next（不签字、不改正式档案）
│   ├── blind_test.py         ← S7：盲测包 + 评分
│   ├── 10_export_gate.py     ← S2：导出落盘门禁
│   └── 11_finalize_download.py ← S2：.crdownload 收尾
├── templates/                ← 6 份空白模板（00–04 + AGENTS）
├── examples/                 ← 合成样例，不是真人访谈
├── docs/                     ← 设计/标准/评分卡/安装/环境文档
└── tests/                    ← pytest 回归；改脚本必须跑
```

## 4. 命令地图（复制就能跑）

```powershell
# 0. 体检 + 初始化
python -X utf8 scripts/xh.py doctor
python -X utf8 scripts/xh.py init

# 1. 只有 raw：一条命令出初稿（会自动探测 work/interview）
python -X utf8 scripts/xh.py build --raw work/raw --db work/unified_index.db --kit work/kit --l2 work/layer2

# 2. 分步跑（每步只看一个信号）
python -X utf8 scripts/xh.py ingest --raw work/raw --db work/unified_index.db --query 记错
python -X utf8 scripts/xh.py match --db work/unified_index.db --out work/backfill_candidates.md
python -X utf8 scripts/xh.py validate --kit work/kit --strict

# 3. 二次回流（候选；签字前不许写正式档案）
python -X utf8 scripts/xh.py backfill --profiles work/kit --first-pass work/backfill_candidates.md --db work/unified_index.db --out work/layer2
python -X utf8 scripts/xh.py backfill --out work/layer2 --init-signing-key
python -X utf8 scripts/xh.py backfill --out work/layer2 --sign L2-0001 --status signed --by "芯火"
python -X utf8 scripts/xh.py backfill --profiles work/kit --out work/layer2 --apply-signed --confirm

# 4. 验收 / 盲测 / 打包
python -X utf8 scripts/xh.py review --confirm --kit work/kit
python -X utf8 scripts/xh.py verify --kit work/kit --strict
python -X utf8 scripts/xh.py blind --kit work/kit --out work/blind
python -X utf8 scripts/xh.py blind --kit work/kit --out work/blind --score work/blind/盲测三问.md
python -X utf8 scripts/xh.py package --out dist/xh-dossier.zip
```

## 5. 卡点决策树（按“看到什么”跳）

| 你看到的信号 | 最可能的原因 | 先做这一件事 | 不要做 |
|---|---|---|---|
| `DOCTOR_FAIL` / 缺 Python | 环境没装或 PATH 不对 | 按 README 3.0 装 Python 3.11+，再跑 doctor | 不要手改脚本绕过 |
| `ENV_BLOCKED: login` | 浏览器没有本人登录态 | 交还本人登录/扫码；Agent 不代登录 | 不要抓 Cookie、不要用别人账号 |
| `EXPORT_DIR_MISSING` | raw 目录路径错/没建 | 核对盘符/路径；`mkdir` 后重跑 | 不要继续 ingest 空目录 |
| `EXPORT_BUTTON_MISSING` | 扩展/脚本没装，或本人没点导出 | 按 `docs/00-install-one-click.md` 装 AfterChat；本人点导出 | 不要自建接收后台 |
| `DOWNLOAD_INTERRUPTED` / `.crdownload` | 浏览器下载没完成 | 等下载完成，或 `11_finalize_download.py` | 不要把半截文件当 `.md` |
| `INDEX_OK(0)` | 导出格式不是可识别格式 | 看 `01_clean_and_index.py` 的识别格式；重导 | 不要手写假 raw |
| `FOUR_WAY_OK` 但候选很少 | 查询词太窄/数据少 | 换关键词、补导出；看报告里的 `REC-` | 不要拿空报告宣布“没有事实” |
| `VALIDATE_FAIL` | 占位符、缺槽位、引用不可追溯 | 按报错逐条补；A 级只认访谈摘要，B 级才认 raw | 不要把 `[待确认]` 改成确定句 |
| `SCORECARD_FAIL` | 覆盖/可答/引用/主线收敛不达标 | 看 `docs/scorecard.md`，补事实或裁主线 | 不要只改阈值骗绿灯 |
| `VALIDATE_OK_SCORECARD_FAIL` | 结构过了，评分卡没过 | 当成“未完成”，继续补 | 不要当 `VALIDATE_OK` 发布 |
| `SIGNING_KEY_MISSING` | 没生成本机签名 key | `backfill --out ... --init-signing-key` | 不要手改 `l2_review.jsonl` 的 `status` |
| `SIGNATURE_INVALID` / `AUDIT_*` | ledger 被手改/复制/重排 | 停；恢复原 ledger/重新签字 | 不要 `--apply-signed` 硬写 |
| `VERIFY_BLOCKED_REVIEW` | 6 份档案还没本人复核 | `review --confirm --kit work/kit` | 不要 Agent 代签 |
| `BLIND_FAIL` | 换 Agent 后答不出主线/准则/硬规则 | 回 S1/S6 补事实，重做盲测 | 不要改作答表/背答案 |
| `BLIND_SCORE_MISSING` | `--score` 路径不存在 | 先 `blind` 生成，再填写作答 | 不要空表评分 |
| `FINALIZE_NONE` | 没有 `.crdownload` | 正常；检查浏览器是否已直接保存 | 不要反复重试 |

## 6. 当前上线门（2026-11-25）

**结构门（必须全绿）**

- `python -X utf8 -m pytest -q --disable-warnings` 全绿；
- `demo` 在空 `work/` 与有真实 `work/raw` 两种场景都 `DEMO_OK`；
- 真实两会话链路：`INDEX_OK → FOUR_WAY_OK → BOOTSTRAP_OK(interview>0) → VALIDATE_OK → BLIND_PASS`；
- `apply-signed` 对手改 ledger 必须拒绝，对正常签字必须写入且留审计。

**产品门（必须人过）**

- 本人能看懂 `01` 当前主线、`02` 三条判断、`03` 硬规则、`04` 正反例；
- 换一个全新 Agent，只给 6 份档案，三问能答对；
- 浏览器导出由本人完成，Agent 不代登录、不代点“另存为”、不代签字。

**对外发布门（另开一关）**

- AfterChat 扩展路径真实跑通，不是只跑 DOM 兜底；
- 干净机器/干净用户目录能按 README 从零装到 `DOCTOR_OK`；
- 有可回滚的发布包和 SHA256。

## 7. 硬边界（写进任何 Agent 的默认行为）

- 不伪造访谈答案；不确定就写 `[待确认]`，并给原文/出处。
- 不把 assistant 的总结、思考过程、提示词当用户记忆。
- 不把“提及时间”当“事件时间”。
- 不替本人签字；`--apply-signed` 只能在本人逐条确认后执行。
- 不抓别人的聊天、Cookie、密码、验证码；不把登录态写进 raw。
- 不因为用户没装扩展就自建后台；缺件就停，给官方安装入口。
- 不把 `VALIDATE_OK` 当“可交付”；还要 review + 盲测。
- 改脚本必须补/跑测试；不要把终端日志当产品。

## 8. 改代码的最小验证

```powershell
# 快速：目标测试
py -3.12 -m pytest -q tests/test_validate_fixes_t2.py tests/test_deep_backfill.py tests/test_blind_test.py --disable-warnings

# 全量：合并前
py -3.12 -m pytest -q --disable-warnings

# 端到端：合成样例
python -X utf8 scripts/xh.py demo
```

如果 `demo` 与真实 `work/raw` 同时存在，`demo` 必须只读 `examples/sample_raw`，不能被真实 raw 污染（P2）。
