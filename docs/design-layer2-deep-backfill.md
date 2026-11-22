# xh-dossier 二次回流（Layer-2 Deep Backfill）机制任务书

> 调研日期：2026-11-22 ｜ 性质：Read-only 调研 + 可执行任务书（**本次不改项目代码**）
> 目标项目：`E:/项目工作区/test-xh-dossier`
> 交付物：本文件 `E:/个人知识库/outputs/二次回流机制任务书.md`
>
> **标注约定**（与同系列《检索第3-4层落地任务书》一致）：
> `[代码确认]` = 已读项目源码/脚本确认；`[数据确认]` = 已查 `work/real_index.db` 与 `work/*.md` 实跑输出确认；
> `[档案确认]` = 已读 `E:/芯火知识库/芯火知识库/个人知识库/00-热加载核心/` 六份档案确认；
> `[用户原话]` = 用户在本任务中的直接表述；`[设计推断]` = 本任务书的设计主张/推断，**未被代码或数据证实**。

---

## 0. 核心结论（先看结论）

1. **用户对"第二次回流还没做"的理解是对的**，但理由要更精确。原型 `scripts/04_second_pass_backfill.py` 确实"反向挖"了，但它**没有把"第一次回流后的档案"当输入**，也**没有任何写回档案或签字的代码**——它只是又生成了一份候选报告。缺的不是"再扫一遍数据库"，而是**"以已回流档案为输入的第二遍 + 写回六份档案 + 人工复核签字"的闭环**。`[代码确认]`

2. **对第一层回流的描述有两处需要校正，一处口径要澄清**：`[代码确认][档案确认]`
   - 校正 A：`02_four_way_match.py` **不负责"把 `[待确认]` 转正"**，它只产出带 `[待确认]` 的候选报告（`scripts/02_four_way_match.py:330`）；转正按档案规矩必须由本人真实签字（`AGENTS.md:33`）。且六份档案正文当前**没有** `[待确认]` 标记——说明"写回档案"这一动作至今仍在人工侧，代码里不存在。
   - 校正 B：`02_four_way_match.py` **没有"时间关键点"入参**（`run_four_way_pipeline` 参数只有 db / keywords / use_fastembed / cluster_threshold / pattern_threshold，`main` 也无时间参数）；`created_at` 只是候选报告里的展示字段，且是 `YYYY-MM-DD` 日期粒度。用户说的"按时间关键点进去做一次回流"是对**人工工作方式**的描述，不是脚本行为。
   - 澄清 C：热加载文件实际是 **6 份**（`AGENTS.md` + `00`~`04`），不是 5 份；且模板里第 6 份叫 `04-正反例避坑账.md`，真实基准叫 `04-反面案例清单.md`（`templates/` 与 `00-热加载核心/` 命名不一致）。本任务书按**实际基准 6 份**、以 `04-反面案例清单.md` 为准。

3. **真实数据上的误报是确定性工程缺陷，不是"调调阈值"能解决的**：`[数据确认]` 729 条原文（user 346 / assistant 383）上，`04` 挖出的重复短语 Top20 全是「可以看一下」(90 条)、「你可以看一下」(77 条)、「我觉得你可以」(68 条) 等口语助词；16 条"语义错配"里混入了 600+ 字的排课驾驶舱长提示词（REC-0018）、播客稿/智能总结（REC-0030、REC-0270）、技能调用卡片（REC-0158/0182/0457）和 URL 指令（REC-0489）。根因是**纯字符 n-gram + 全条 marker 计数 + 把「role=user」等同于「本人亲历」**。

4. **可执行的最小路径**：新增独立脚本 `scripts/05_deep_backfill.py`（**不改** 02/04），做"三输入 → 七步 → 三输出"的确定性流水线。纯规则可完成去重、视角门禁、助词过滤、分句否定、写回格式、签字状态机；**语义归并与摘要必须 LLM**，无 LLM 时降级为"原文摘录 + 证据字段 + 人工全量阅读"，脚本绝不编造提炼句。`[设计推断]`

---

## 1. 两层回流的准确定义与理解确认

### 1.1 用户原话与本任务书的对照

| 用户原话要点 | 本任务书理解 | 判定 |
|---|---|---|
| "目前我们其实只做了一次回流，就是根据时间关键点进去做一次回流" | 第一层 = 一次性从冷库按预设关键词 + 3 个硬编码模式召回候选，人工按 `created_at` 时间点复核 | 方向正确，但"时间关键点"不是脚本入参（校正 B） |
| "第二次回流其实还是没做" | 缺的是"以第一层结果之上的档案为输入的第二遍 + 写回 + 签字闭环" | **理解正确**（见 §1.3） |
| "二层回流主要是从我们获取的数据库中进行去重，找到除了我们所讲的那些内容之外，还有一些我们没讲到的信息" | L2 的核心判据是 **db 里有、档案里没有**，即"差集挖掘"，不是"换个关键词再查一遍" | 完全一致 |
| "找重复的内容；找我们抱怨过的一些东西，以及一些反复出现的错误；挖掘更多信息，然后进行再次深度回流" | L2 的三类信号：跨对话复现、抱怨、反复错误；输出必须能"再次深度回流"进档案 | 一致，但需视角门禁（§4.2） |
| "它不仅仅是根据我们所讲的内容去纠错，以及根据我们所讲的内容去寻找关系网，我觉得同样可以根据我们没讲的一些东西来获取价值" | L1 是"验证讲过的"（纠错/关系网），L2 是"发现没讲过的"（增量价值）。两者是**串联的两遍**，不是同一遍的两种模式 | 一致 |

### 1.2 两层的严格区分 `[代码确认][设计推断]`

| 维度 | 第一层回流（已有，02 脚本） | 第二层回流（待建，05 脚本） |
|---|---|---|
| 输入 | 冷库 `unified/real_index.db` + 预设关键词 + 3 个硬编码模式种子 | **① 第一次回流后的 6 份档案当前正文**；② 第一层候选报告（`[待确认]` 清单）；③ 冷库原文 |
| 问题 | "我讲过的内容，原文能不能证实？" | "我**没讲过**的内容里，有什么值得进档案？" |
| 检索方向 | 正向：关键词 / TF-IDF / 去均值聚类 / 模式磁铁 | 反向：先建"已覆盖集合"，再取 db 的**差集** |
| 依据 | 预设关键词 + `DEFAULT_PATTERNS`（ai_misunderstood_user / affirmative_action / method_principle，`02:195-199`） | 无预设模式；信号来自重复度、抱怨度、错误复现度 + 视角门禁 |
| 门禁 | 主宾反转 + 否定词（`apply_guardrails`，`02:179-192`） | 复用主宾/否定 + 新增"用户视角 / 非个人材料 / 跨文件重复"门禁（§4） |
| 输出 | `backfill_candidates.md`：全部 `[待确认]` 候选 | `second_pass_candidates.md` + 逐档案补丁 + 签字台账：全部 `[待确认]`，签字后才生效 |
| 写回档案 | **无代码**（人工侧） | 有明确写回格式与签字状态机（§3.4~3.6） |
| 一次运行性质 | 一次性扫描 | **作用于 L1 结果之上的第二遍**（必须读档案，不能只读 db） |

**一句话判据**：L1 问"讲过的对不对"，L2 问"没讲的是否有价值"；L2 必须能回答"这条在档案里出现过吗"，否则就不是第二层。

### 1.3 为什么"第二次回流还是没做"——对 04 原型的逐项核对 `[代码确认]`

`04_second_pass_backfill.py` 做了什么、没做什么：

| 环节 | 04 原型 | 判定 |
|---|---|---|
| 读 db | `load_records(db)`（`:27-35`） | 做了 |
| 读第一层结果 | `load_pattern_claims(backfill_md)`（`:38-58`）——**只读候选报告，不读档案正文** | 缺口 1：输入不是"第一次回流后的档案" |
| "覆盖"定义 | `semantic_mismatch = 没有非 keyword-only 的模式 claim`（`:110-112`） | 缺口 2：判据是"模式覆盖"，不是"档案覆盖" |
| 反挖信号 | 抱怨 marker 计数、错误 marker 计数、字符 n-gram 重复（`:61-93`） | 做了，但误报严重（§2.3） |
| 写回档案 | `main()` 只 `args.out.write_text(render_report(...))`（`:168-183`） | 缺口 3：**零写回代码** |
| 复核签字 | 无状态、无台账、无签字占位 | 缺口 4：闭环缺失 |
| 语义错配输出 | 报告第三节列出建议（真实输出 16 条，见 `work/real_second_pass.md:6906+`） | 做了，但混入提示词/播客稿/技能卡片 |

**结论**：用户说"第二次回流还是没做"**准确**。04 只是"一次额外的候选扫描"，不满足"作用于 L1 结果之上 + 写回 + 签字"的第二遍定义。即使把它接上写回，若不修 §4 的误报，写回的全是垃圾。

---

## 2. 现状事实基线

### 2.1 脚本链 `[代码确认]`

| 脚本 | 职责 | 关键事实 |
|---|---|---|
| `00_export_wizard.py` | 导出向导（需同意、支持 dry-run） | 与回流无直接关系 |
| `01_clean_and_index.py` | 清洗/MD5 去重/FTS5 建库 | `records(rec_id,source_file,created_at,role,content,md5)` + `records_fts(trigram)`（`:220-230`）；`rec_id = REC-%04d`（`:258`）；AfterChat emoji 格式解析（`:148-170`）；`search_keyword` 走 FTS5（`:276-313`） |
| `02_four_way_match.py` | 第一层四路匹配 | 关键词 + 向量(可选 fastembed) + 去均值聚类 + 模式磁铁；主宾/否定门禁；输出全为 `[待确认]` |
| `03_validate_kit.py` | kit 模板校验（占位符/PII/禁词） | 测试里验证 6 份模板文件、`[待确认]` 规则文字、PII 拦截（`tests/test_pipeline.py:183-219`） |
| `04_second_pass_backfill.py` | 二层原型 | 见 §1.3 |
| `tests/test_pipeline.py` | 现有 9 组 pytest | 风格：模块 `import_module`、tmp_path 建临时 db、断言报告字符串与状态 |

### 2.2 数据库与真实数据 `[数据确认]`

```
work/real_index.db:  records = 729 行
role 分布:          user 346 / assistant 383
created_at = 'unknown': 0 行      → 用户说的 emoji 解析修复属实
user 记录中 >600 字: 60 行         → 长提示词/技术文档误报源
user 记录中含"播客/收听": 16 行     → 播客稿/智能总结误报源
含"可以看一下"的 90 行全部是 role=user
```

- `rec_id` 格式为 `REC-0001`~`REC-0729`，与 02/04 报告里的 `REC-\d{4}` 解析正则一致。
- `created_at` 为日期粒度（`YYYY-MM-DD`），无时分秒；这与同系列任务书关于"双时态只能模拟"的结论一致。

### 2.3 误报复现 `[数据确认]`

**误报 A：重复短语全是助词**（`work/real_second_pass.md:8-27`）

```
「可以看一下」90 条 →「你可以看一下」77 →「我觉得你可以」68 →「，你可以看」46 →「可以看一下，」45 → …
「对应的一个」29 →「这里的话，」20 → …
```

根因：`find_repeated_phrases`（`04:73-93`）对 5~8 字字符 n-gram 只做"含汉字 + 跨 2 条记录"判断，无停用词、无词性、无"跨对话"约束。中文口语的高频虚词天然满足"重复"，于是淹没真信号。

**误报 B：播客稿/提示词/技能卡片被当抱怨**（`work/real_second_pass.md:6906+`）

```
REC-0018  →「你是一名同时精通 Timefold Solver 2.5…」（600+ 字长提示词）
REC-0030  →「[Seed Audio 1.0](skill://…) # 正则表达式实战播客稿 · 爬虫篇」
REC-0270  →「…📑 智能总结 内容信息 - 时长…」
REC-0158/0182/0457 → skill:// / plugin:// 技能调用卡片
REC-0489  →「https://github.com/… 你需要去上面这个网址把…」（URL 指令）
```

根因：`complaint_score` / `mistake_score`（`04:61-67`）按整条 marker 命中计数，`COMPLAINT_MARKERS` 含「实在 / 又 / 居然 / 错了 / 反复 / 每次都要」等虚词与通用词；`role == "user"` 被直接等同"本人亲历"，而真实导出里 user 轮次大量是**粘贴给 AI 的材料**（提示词、播客稿、总结、链接、技能卡）。

**误报 C：否定句只标注不拦截**：`has_negation`（`04:69-70`）只输出 `⚠否定句` 标签，仍把它列入候选（`04:120, 153`）。"先不要帮我改…别直接替我重写"这类**明确否定**照样进入 L2 建议。

### 2.4 档案结构与签字规矩 `[档案确认]`

- 六份：`AGENTS.md`、`00-总入口索引.md`、`01-身份与当前主线.md`、`02-核心判断准则.md`、`03-硬规则与表达黑话.md`、`04-反面案例清单.md`。
- 关键章节锚点（用于 L2 回填定位）：
  - `04`：`## 一、正例标本` / `## 二、反例标本（13 笔…）`，条目格式为 `### 反例 N（日期）· 标题` + `实证经过` + `铁律`。
  - `02`：`## 一、道` / `## 二、法` / `## 三、术` / `## 四、器`。
  - `01`：`## 一、不可篡改的核心事实` / `## 二、当前主线定调与明确放弃项`。
  - `03`：`## 一、对任何接手 AI 的 11 条硬规则` / `## 三、核心黑话与已纠偏词典`。
  - `00`：`## 二、七步闭环流程`（一般只放指针，不堆细节）。
- 硬规矩：`AGENTS.md:33`——"`02-资产/` 预铸卡或过程归档在终签前统一标 `[待本人最终签字放行]`，只有经芯火本人真实检查并签字确认后才算正式结项生效"；`AGENTS.md:32`——独立上下文 AI 双尺审查（Standards + Spec）≤ 3 轮。**六份档案正文当前没有 `[待确认]` 字样**，L2 必须自带待确认区且不碰正式正文。

---

## 3. 第二层回流完整机制设计 `[设计推断]`

### 3.1 输入（三路，缺一不可）

| 输入 | 路径 | 用途 |
|---|---|---|
| **A. 第一次回流后的档案正文** | `E:/芯火知识库/芯火知识库/个人知识库/00-热加载核心/{AGENTS.md,00~04}.md`（只读） | 构建"已讲过集合"： extracts 已有 `REC-` 引用、日期、主题实词、正/反例标题 |
| **B. 第一层候选报告** | `work/real_backfill.md`（含 `[待确认]` 与模式归属） | 区分"已进 L1 待确认"与"L1 完全没召回"；避免 L2 与 L1 重复产出 |
| **C. 冷库原文** | `work/real_index.db`（`records` 表） | 差集挖掘的数据源 |

> 关键：**只给 C 不给 A/B，就还是 04 原型**。脚本启动时应强制校验 A 目录可读、B 文件存在，否则拒绝运行并报 `MISSING_FIRST_PASS_INPUT`。

### 3.2 处理步骤（七步流水线）

```
S1 读档案 → build_coverage_index(A)：得到 covered_rec_ids + covered_topic_terms（按档案章节分桶）
S2 读 L1 报告 → parse_first_pass(B)：得到 pending_rec_ids + pattern_claims
S3 读冷库 → load_records(C)，按 role=user 过滤得到候选池（346 条）
S4 逐条过"非个人材料门禁"（§4.2）：提示词 / 播客稿 / 智能总结 / 技能卡 / URL 指令 / >600 字 → non_personal 剔除
S5 实词化重复短语挖掘（§4.1）：跨 source_file ≥2、去掉助词停用词、保留实词 n-gram
S6 分句级信号判定（§4.3 + §4.4）：抱怨 / 反复错误 / 复现主题，逐句做否定与主宾门禁
S7 差集裁决（§4.5）：signal_pass ∧ ¬covered_by_profile ∧ ¬claimed_by_real_pattern → L2 候选；
    已在 B 的 `[待确认]` 里则标 `cross_ref=L1` 而非重复产出
```

### 3.3 输出（三件）

1. **`work/l2_candidates.md`（主报告）**：每条候选含 `[待确认]`、`L2-NNNN`、`REC-id | created_at`、信号类型、证据字段（复现次数/跨对话数/分句得分）、建议档案与章节、`source_file` 溯源。
2. **`work/l2_profile_patches/<档案名>.patch.md`（逐档案补丁）**：只含"待确认区"区块（格式见 §3.5），**不触碰正式正文**。
3. **`work/l2_review.jsonl`（签字台账）**：每行 `{candidate_id, rec_id, layer:2, status, reviewer, reviewed_at, signed_at, note}`，状态机见 §3.6。

### 3.4 回填位置映射 `[设计推断]`（需本人最终拍板）

| 信号 | 目标档案 | 具体章节 | 落地形式 |
|---|---|---|---|
| 反复错误 / 踩坑复现 | `04-反面案例清单.md` | `## 二、反例标本` 新增「反例 14…」 | 日期 + 经过 + 铁律（对齐现有 13 笔格式） |
| 正向复现的好模式 | `04-反面案例清单.md` | `## 一、正例标本` 新增「正例 4…」 | 同上 |
| 抱怨 / 卡点 / 没交付 | `02-核心判断准则.md` | `## 三、术` 或 `## 四、器` | 判断准则条目，带原话证据 |
| 忘了写的核心事实 | `01-身份与当前主线.md` | `## 一、不可篡改的核心事实` | **必须本人确认**，脚本只出候选 |
| 新硬规则 / 黑话纠偏 | `03-硬规则与表达黑话.md` | `## 一` / `## 三` / `## 四` | 需本人拍板后才升格 |
| 索引 / 流程变更 | `00-总入口索引.md` | `## 二、七步闭环流程` | 一般只加温加载软指针，不堆细节 |
| `AGENTS.md` | — | — | **默认只读不写**；如确需改规矩，由本人手动改 |

### 3.5 `[待确认]` 标注与补丁格式 `[设计推断]`

每个补丁文件末尾追加**受控区块**（脚本只在此区块内增删）：

```markdown
<!-- L2-BACKFILL-BEGIN · 机器生成 · 未经本人签字不生效 -->
## 附：二层回流待确认区

### L2-0007 [待确认] [REC-0348 | 2026-09-24] 建议位置：04-反面案例清单 / 二、反例标本
- **信号**：抱怨分 2 ｜反复错误分 1 ｜跨 3 个对话复现
- **证据**：`source_file=xxx.md`；分句「…」命中 marker「每次都要…」
- **原文摘录**：> （原文 1~3 句，不改写、不编造）
- **L1 关系**：L1 未召回（非 `[待确认]` 条目）
- **复核**：□ 本人亲历  □ AI 代做/转述/材料  □ 已讲过  □ 值得升格
- **独立 AI 双尺审查**：□ 规范尺  □ 需求尺（≤ 3 轮）
- **本人签字**：__________  日期：__________
<!-- L2-BACKFILL-END -->
```

- `[待确认]` 是**唯一合法初始状态**；签字后由人工剪入正式章节并改成该档案原生条目格式（如 `### 反例 14（日期）· 标题`），同时从待确认区移除。
- 脚本提供 `--apply-signed`（仅把 `status=signed` 的条目按 §3.4 映射插到章节锚点前），且需显式 `--confirm` 二次确认；**默认不自动改正式正文**。

### 3.6 复核签字状态机 `[设计推断]`

```
pending ──独立AI双尺审查(≤3轮)──> reviewed ──本人真实签字──> signed ──--apply-signed──> archived
   └───────────────┬──────────────────────┬──────────────────────┘
                   ▼                      ▼
               rejected              needs_llm（语义判断未做，不得跳过）
```

- `signed` 必须记录签字人与时间；无签字记录的条目在 `l2_candidates.md` 中始终显示 `[待确认]`。
- "本人亲历"是硬门禁：`□ AI 代做/转述/材料` 被勾选即 `rejected`（对齐 `AGENTS.md:42` "禁止把 AI 代做成果冒充本人原子卡"）。
- `needs_llm` 状态显式暴露给用户，不伪装成通过（详见 §7）。

---

## 4. 误报治理：可落地、可验证的过滤规则 `[设计推断]`

### 4.1 重复短语：从"字符 n-gram"改为"实词 n-gram + 跨对话"

| 规则 | 实现 | 验证 |
|---|---|---|
| 停用虚词切除 | `STOPWORDS = {可以,看一下,看一下，,一下,我觉得,我觉,这里,的话,那个,这个,其实,就是,可能,应该,一些,进行,相关,对应,一个,然后,反正,好像,有点,我们,这个，}`；gram 去掉停用词后剩余长度 ≥ 3 汉字 | 「可以看一下」「你可以看一下」「对应的一个」「这里的话，」全部出局 |
| 实词约束 | gram 必须至少含 1 个实词字符来自 `CONTENT_HINT`（动词/名词常用字集合，可配置扩展）；若装了 `jieba.posseg`，用词性 `n/nr/nz/v/vn/a/an` 过滤，排除 `r/p/u/c/d/t/y` | 「开工先定验收标准」「做完一直没发出去」保留 |
| 跨对话约束 | 同一 gram 必须出现在 **≥2 个不同 `source_file`**，而非仅 2 条记录 | 单一对话内口头禅不再成"主题" |
| 标点边界 | gram 不得跨 `。！？；\n` 切分 | 避免拼接出伪短语 |
| 长度与去重 | `4 ≤ len(g) ≤ 12`，最长匹配去子串（沿用 `04:87-93` 思路但作用于实词 gram） | 不再输出 20 条同义助词串 |

阈值初值：`min_docs=2`、`min_len=4`、`max_len=12`；用 `work/real_index.db` 回归，要求 Top20 中助词类占比 = 0。

### 4.2 用户视角门禁：把"role=user"还原成"本人亲历"

逐条判定 `classify_narrative(content) -> (bool, reason)`，**任一命中即 `non_personal` 剔除**：

| 排除模式 | 正则/前缀示例 | 真实数据命中 |
|---|---|---|
| 指令式长提示词 | `^你是一名` / `^你是` / `绝对铁律` / `^任务[:：]` / `^# 角色` | REC-0018、REC-0158 |
| AI 思考/总结/播客稿 | `📑 智能总结` / `#### 🤔 Thought Process` / `播客稿` / `播客访谈文字稿` / `感谢收听` | REC-0030、REC-0270 |
| 技能/插件卡片 | `skill://` / `plugin://` / `[操作电脑]` / `[Seed Audio` / `[GitHub]` | REC-0158/0182/0457 |
| 纯 URL 指令 | `^https?://` 或正文含 `去上面这个网址` | REC-0489 |
| 超长材料 | `len(content) > 600` | 真实库 60 条 |
| 无第一人称经历 | 不含 `我 / 我们 / 本人 / 上次 / 最近 / 当时 / 结果 / 后来` 中至少 1 个 | 大量技术文档 |

**保留条件**（需同时满足）：`role=user` ∧ 长度 `15 ≤ len ≤ 600` ∧ 通过上表 ∧ 至少一个"经历标记"句。

> 诚实边界：这层规则是**初筛**，不是语义判决。"我朋友说他每次都…"仍可能漏网；"我把播客稿贴给你，我想听"也可能误杀。因此每条候选保留 `needs_llm` 标记供人工/LLM 复核（§7）。

### 4.3 语句级否定与主宾门禁

- **分句**：按 `[。！？!?\n；;]` 切句，每句独立打分，不再整条 content 计数。
- **否定拦截**：若某句命中 `NEGATION = ("先不要","不要","先别","别直接","禁止","绝不","别帮我")` 且否定词出现在句首 12 字内 → 该句 `negation_filtered`，**不计入抱怨/错误信号**（`04` 原样只是加 `⚠` 标签，仍输出）。
  - 反例验收：「先不要帮我改完一直没发出去那版网页…别直接替我重写」→ 0 信号。
- **主宾门禁**（复用 02 的成熟门禁）：`SUBJECT_USER_MISS = ("我没听懂","我没看懂","没明白你说的")` 与 `SUBJECT_AI_MISS = ("你还是没理解","你没理解","没听懂你讲")`；若句子只有 user-miss 无 ai-miss → 不判为 `ai_misunderstood`（对齐 `02:183-186` 的 `subject_object_inversion`）。
- **第一人称主语**：只有含"我/我们/本人"作主语的句子才计入"我的抱怨/我的错误"；"你每次都要…"这类**对 AI 的指令**不计入本人踩坑。

### 4.4 语义错配判据修正：从"模式覆盖"改为"档案覆盖"

`04` 的 `semantic_mismatch`（`:110-112`）问的是"有没有模式 claim 它"，在真实数据上 346 条 user 中只有 62 条被 claim，于是 284 条天然"错配"，垃圾涌出。改为三层判据：

| 层级 | 判据 | 输出 |
|---|---|---|
| C0 | `covered_by_profile`：`rec_id` 已在档案正文，或 content 的实词集合与某档案章节实词集合共现 ≥2 个 | 不产出（已讲过） |
| C1 | `in_l1_pending`：`rec_id` 在 B 的 `[待确认]` 列表 | 标 `cross_ref=L1`，交叉引用不重复产出 |
| C2 | `claimed_by_real_pattern`：在 B 的模式章节被真实模式 claim | 不产出（L1 已覆盖） |
| C3 | 以上皆否 + §4.1~4.3 全过 | **L2 候选**（真正的 untold） |

### 4.5 规则可验证性对照

| 规则 | 合成库（10 条 regress）期望 | 真实库（729 条）期望 |
|---|---|---|
| 助词过滤 | 「开工先定验收标准」「做完一直没发出去」保留 | Top20 无「看一下」类助词 |
| 视角门禁 | REC-0001~0010 全保留 | REC-0018/0030/0270/0489 全剔除 |
| 否定拦截 | REC-0008（"先不要…"）0 信号 | 长提示词中的"禁止…"不入抱怨分 |
| 主宾门禁 | 02 已拦截的 REC-0007 不复活 | 不产生 ai_misunderstood 误判 |
| 差集裁决 | REC-0002 若在 L1 待确认则标 cross_ref | 16 条"语义错配"应降到个位数且全为本人亲历 |

---

## 5. 具体文件 / 函数设计 `[设计推断]`

### 5.1 新增 `scripts/05_deep_backfill.py`（不改 02/04）

```python
# 常量
STOPWORDS: set[str]
CONTENT_HINT: set[str]
NON_PERSONAL_PREFIX: tuple[str, ...]
NEGATION: tuple[str, ...]
SUBJECT_USER_MISS / SUBJECT_AI_MISS: tuple[str, ...]
PROFILE_FILES: tuple[str, ...] = ("AGENTS.md", "00-总入口索引.md", "01-身份与当前主线.md",
                                  "02-核心判断准则.md", "03-硬规则与表达黑话.md", "04-反面案例清单.md")
PROFILE_SECTION_MAP: dict[str, str]   # 信号类型 → (档案名, 章节锚点)

# 核心函数
def load_profiles(profile_dir: pathlib.Path) -> dict[str, str]
def build_coverage_index(profiles: dict[str, str]) -> CoverageIndex
    # CoverageIndex(covered_rec_ids:set[str], terms_by_section:dict[str,set[str]])
def parse_first_pass(backfill_md: pathlib.Path) -> FirstPassIndex
    # FirstPassIndex(pending_rec_ids:set[str], claims:dict[str,list[str]])
def load_records(db_path: pathlib.Path) -> list[dict[str, str]]      # 复用 01 的 schema
def classify_narrative(content: str) -> tuple[bool, str]             # §4.2 视角门禁
def split_sentences(content: str) -> list[str]                      # §4.3
def sentence_signals(sentences: list[str]) -> SignalResult           # §4.3 否定/主宾/第一人称
def mine_repeated_phrases(records, stopwords, min_docs=2, min_len=4, max_len=12) -> list[PhraseHit]
def coverage_decide(candidates, coverage, first_pass) -> list[L2Candidate]   # §4.4 C0~C3
def render_candidates(candidates: list[L2Candidate]) -> str          # 主报告
def render_patches(candidates, profiles) -> dict[str, str]           # 逐档案待确认区
def load_review_ledger(path) -> dict[str, dict]                      # l2_review.jsonl
def update_review(path, candidate_id, status, reviewer, note) -> dict
def apply_signed(patches_dir, profiles_dir, ledger, confirm: bool) -> dict  # 仅 signed 且 confirm
def run_deep_backfill(profiles_dir, backfill_md, db_path, out_dir, llm_mode="off") -> dict
def main() -> int
```

### 5.2 CLI 契约

```bash
# 生成候选（只读，不改档案）
python -X utf8 scripts/05_deep_backfill.py \
  --profiles "E:/芯火知识库/芯火知识库/个人知识库/00-热加载核心" \
  --first-pass work/real_backfill.md \
  --db work/real_index.db --out work/l2_candidates.md \
  --patches work/l2_profile_patches --ledger work/l2_review.jsonl

# 审查/签字（改台账，不改档案）
python -X utf8 scripts/05_deep_backfill.py --ledger work/l2_review.jsonl --sign L2-0007 --by "芯火"

# 仅把已签字条目写回正式正文（二次确认）
python -X utf8 scripts/05_deep_backfill.py --apply-signed --confirm ...
```

### 5.3 与现有代码的衔接

- **复用**：`01_clean_and_index.py` 的 db schema 与 `search_keyword`（溯源查原文）；`02_four_way_match.py` 的 `apply_guardrails` / `SUBJECT_USER_MISS` / `SUBJECT_AI_MISS`（门禁一致性）。
- **不复用**：`04` 的 `find_repeated_phrases` / `complaint_score` / `mistake_score` / `semantic_mismatch`（误报根因，保留作回归反例）。
- **回归数据**：`work/regress_index.db`（10 条合成）做规则单测；`work/real_index.db`（729 条真实）做误报率验收。

---

## 6. pytest 验收断言（12 条，≥8）`[设计推断]`

新增 `tests/test_deep_backfill.py`，沿用 `tests/test_pipeline.py` 的 `import_module` + `tmp_path` 风格：

```python
# 1. 视角门禁：长提示词剔除
ok, reason = mod05.classify_narrative("你是一名资深全栈工程师…绝对铁律…" * 20)
assert not ok and reason == "instructional_prompt"

# 2. 视角门禁：播客稿/智能总结剔除
ok, reason = mod05.classify_narrative("📑 智能总结\n内容信息\n- 时长：约 44 分钟…感谢收听")
assert not ok and reason in {"forwarded_summary", "podcast_transcript"}

# 3. 视角门禁：本人亲历保留
ok, _ = mod05.classify_narrative("上次我的小工具做完一直没发出去，拖了四天，结果错过截止")
assert ok

# 4. 助词过滤：真实库上 Top20 无口语助词
hits = mod05.mine_repeated_phrases(real_records, min_docs=2)
top20 = [p.gram for p in hits[:20]]
assert not any("看一下" in g or "我觉得你" in g or "对应的一个" in g for g in top20)
assert any("验收" in g for g in top20) or len(hits) == 0  # 无实词主题时允许空

# 5. 跨对话约束：同一 source_file 内的重复不计
one_file = [{"rec_id": f"REC-{i:04d}", "source_file": "same.md", "content": "开工先定验收标准很重要"} for i in range(3)]
assert mod05.mine_repeated_phrases(one_file, min_docs=2) == []

# 6. 否定句拦截：分句级 0 信号
sig = mod05.sentence_signals(mod05.split_sentences("先不要帮我改那版网页，我想自己看懂报错，别直接替我重写"))
assert sig.complaint == 0 and any(s.negation_filtered for s in sig.sentences)

# 7. 主宾门禁：两方向不混淆
a = mod05.sentence_signals(["我没听懂你讲的协程概念，打个比方"])
b = mod05.sentence_signals(["你还是没理解我要的是先原理后代码"])
assert not a.misunderstood_ai and b.misunderstood_ai

# 8. 已覆盖裁决：档案里出现过的 REC 不产出
cov = mod05.build_coverage_index({"04-反面案例清单.md": "### 反例 2（2026-10-12）… [REC-0005] …"})
fp = mod05.parse_first_pass(tmp_path / "empty_first_pass.md")
assert mod05.coverage_decide([fake_rec_0005], cov, fp) == []

# 9. 差集裁决：db 有 + 档案无 + L1 无 → 产出 [待确认]
cands = mod05.run_deep_backfill(profiles_dir, first_pass_md, db_path, out_dir)
assert len(cands) >= 1
assert all(c.status == "pending" and c.rec_id.startswith("REC-") for c in cands)

# 10. 报告格式：每条候选都有签字四件套
md = mod05.render_candidates(cands)
for token in ("[待确认]", "REC-", "本人签字", "独立 AI 双尺审查", "原文摘录"):
    assert token in md

# 11. 签字状态机：未签字不得进已生效输出
mod05.update_review(ledger, "L2-0001", "reviewed", "审查员", "passed")
applied = mod05.apply_signed(patches_dir, profiles_dir, ledger, confirm=True)
assert applied["applied"] == 0
mod05.update_review(ledger, "L2-0001", "signed", "芯火", "本人确认")
assert mod05.apply_signed(patches_dir, profiles_dir, ledger, confirm=True)["applied"] == 1

# 12. 无 LLM 降级：不虚构摘要、显式标注
md_off = mod05.render_candidates(cands, llm_mode="off")
assert "需LLM" in md_off or "原文摘录" in md_off
assert "本条由模型提炼" not in md_off
```

**真实数据验收门槛**（单独脚本/手工跑，不写进 pytest 硬断言以免误伤）：`work/real_index.db` 上候选数应显著小于 04 原型的 16 条，且人工抽查 20 条中"本人亲历"占比 ≥ 80%。

---

## 7. 能力边界：能落地的 vs 必须 LLM 的（不粉饰）`[设计推断]`

### 7.1 纯规则可做（确定性、可 pytest）

- MD5 去重、FTS5 溯源查原文、`REC-id` 解析与差集裁决。
- 停用词/助词过滤、跨 `source_file` 计数、长度与非个人材料前缀门禁。
- 分句否定、主宾反转门禁、第一人称主语约束。
- 候选报告 / 补丁区块渲染、签字台账状态机、`--apply-signed` 受控写回。
- **结论**：L2 的"骨架"（找得到、不写错、签得了字）**完全可以无 LLM 落地**。

### 7.2 必须 LLM 才能做好（语义级）

| 任务 | 为什么规则做不好 |
|---|---|
| "这条是不是本人亲历，还是转述/AI 代做/粘贴材料" | 表面第一人称也可能是转述（"我朋友说他…"）；规则只能初筛 |
| "重复短语是否表达同一个隐含主题" | 「做完没发出去」与「停在最后 10%」字面不同、语义同一，字符/实词 n-gram 合并不了 |
| "这条没讲到的信息值不值得进档案、进哪份哪个章节" | 需要理解个人主线与价值判断，关键词映射会错位 |
| "把原文压成一句可进档案的铁律/判断准则" | 这是提炼与改写，规则只能摘录，不能生成 |
| "抱怨的正负语境"（吐槽 vs 引用别人的吐槽 vs 反讽） | 依赖语用判断 |

**明确表态**：以上内容若不用 LLM，**就没有"深度回流"的"深度"**——只有"候选清单 + 人工全读"。不要拿规则输出冒称已做语义回流。

### 7.3 无 LLM 降级方案（默认路径）

1. `llm_mode="off"` 时，报告每条候选只输出**原文 1~3 句摘录 + 证据字段 + `needs_llm` 标记**，不生成任何提炼句。
2. 把 §7.2 的五个语义任务**全部转成人工复核勾选**（§3.5 的四个 `□`），由本人/独立 AI 审查员逐条判断。
3. 人工全量阅读（不是抽样）是降级的代价；候选数必须靠 §4 规则压到每人可读完的量级（目标 ≤ 30 条/次真实库）。
4. 若后续接 LLM：走 `--llm`，输出中把模型生成的提炼句标注 `[LLM生成·待本人签字]`，且**不得覆盖原文摘录**，与 §7.2 的门禁并存而非取代。
5. 任何情况下：未签字 → 不写正式正文；`needs_llm` 未处理 → 不进 `signed`。

---

## 8. 事实 vs 推断标注清单

| 条目 | 标注 | 依据 |
|---|---|---|
| 02 只产出 `[待确认]` 候选、不转正 | `[代码确认]` | `scripts/02_four_way_match.py:303-335, 338-351` |
| 02 无时间关键点入参 | `[代码确认]` | `run_four_way_pipeline`/`main` 签名 |
| role 346/383、unknown 时间 0 行 | `[数据确认]` | `work/real_index.db` 实查 |
| 重复短语 Top20 是助词 | `[数据确认]` | `work/real_second_pass.md:8-27` |
| 16 条语义错配混入提示词/播客稿/技能卡 | `[数据确认]` | `work/real_second_pass.md:6906+` |
| 04 无写回、无签字代码 | `[代码确认]` | `scripts/04_second_pass_backfill.py:168-183` |
| 六份档案无 `[待确认]` 正文 | `[档案确认]` | `00-热加载核心/` 全库 grep |
| 档案签字铁律与双尺审查 ≤3 轮 | `[档案确认]` | `AGENTS.md:32-33` |
| 模板 `04-正反例避坑账.md` vs 基准 `04-反面案例清单.md` | `[代码确认][档案确认]` | `templates/` 与 `00-热加载核心/` 目录 |
| "第二次回流还没做"理解正确 | `[用户原话] + [代码确认]` | 用户表述 + §1.3 对照 |
| 三输入七步、差集裁决、映射表、状态机、阈值 | `[设计推断]` | 本任务书主张，待实施验证 |
| 哪些语义判断必须 LLM | `[设计推断]` | 基于规则能力边界的推断 |

---

## 9. 实施顺序（里程碑，供排期参考）

1. **M1 规则回归**：实现 `classify_narrative` / `split_sentences` / `sentence_signals` / `mine_repeated_phrases`，在 `regress_index.db`（10 条）上过 §6 断言 1~7。
2. **M2 差集闭环**：实现 `build_coverage_index` / `parse_first_pass` / `coverage_decide`，过断言 8~10；确保 L2 不再输出 L1 已覆盖项。
3. **M3 写回与签字**：实现 `render_patches` / `update_review` / `apply_signed`，过断言 11~12；用临时档案副本验证正式正文未被误改。
4. **M4 真实库验收**：跑 `real_index.db`，核对"助词 Top20=0、16 条错配降到个位数、候选 ≤30 条"，人工抽查 20 条亲历占比。
5. **M5（可选）LLM 增强**：仅在 M1~M4 通过且本人要求时接入，提炼句一律标 `[LLM生成·待本人签字]`。

> **本次任务边界重申**：以上均为任务书设计；未修改 `E:/项目工作区/test-xh-dossier` 任何代码或数据，唯一写入是本文档。

---

## 10. PR #35 独立复审后的修复口径（2026-11-23）

针对独立审查 F1–F9 的落地口径，本节为代码现行行为的权威说明：

- **F1/F2 路径与只读加固**：台账 `target_profile` 属可编辑边界输入。写入前经 `safe_profile_target` 校验——取 `PurePosixPath` 文件名归一化，必须命中 6 档案白名单；拒绝绝对路径、`..` 片段、非白名单名；`(profiles_dir/name).resolve()` 的 parent 必须等于 `profiles_dir.resolve()`（挡符号链接逃逸）。`AGENTS.md` 按归一化后的文件名判定只读；`./AGENTS.md`、`sub/../AGENTS.md`、`../OUTSIDE.md`、绝对路径一律不写入。04 档案的真名 `04-反面案例清单.md` 与模板名 `04-正反例避坑账.md` 互为别名，归一化映射到同一个 canonical 04 文件，不会因命名差异拒绝或写错文件。
- **F3 视角门禁**：非个人材料特征（角色提示词 / 播客转写 / 智能总结 / 技能卡 / URL）先做 NFKC 全角转半角、去空白、小写归一化，再**全文子串**匹配，不再只看前缀。
- **F4 needs_llm 门禁**：台账行持久化 `needs_llm` 与 `needs_llm_resolved`；目标状态为 `signed` 时，若 `needs_llm=true` 且未显式裁决（未走过 `needs_llm → reviewed` 闭环），抛 `NEEDS_LLM_UNRESOLVED`，不得签字。
- **F6 交叉引用分离**：已在一层 `[待确认]` 清单的记录标 `cross_ref=L1`，单列「与 L1 交叉引用」小节，**不计入**二层候选数；候选列表只含真正 untold（`cross_ref=none`）。
- **F8 空一层报告口径（选定方案：拒绝）**：B 文件存在但为空/占位（无 `REC-xxxx` 引用且无 `[待确认]` 标记）时，抛 `MISSING_FIRST_PASS_INPUT` 拒绝运行；不允许空 B 静默产出 untold 候选。
- **F7 archived 落盘**：`--apply-signed` 写回成功后，台账对应行持久化为 `archived` 并记录 `archived_at`，审计链可追溯。
- **F5 短语挖掘现状（诚实标注，未假接线）**：跨对话重复短语命中目前只作为**证据字段**与候选排序键（命中数高者优先），**不参与**纳入/淘汰裁决；仅凭短语命中不升格候选。纳入裁决仍以抱怨/反复错误分句信号为准。语义级跨主题归并留待 LLM 阶段（§7.2）。
