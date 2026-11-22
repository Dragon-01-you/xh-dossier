# xh-dossier 检索第③④层落地任务书

> 调研日期：2026-11-22 ｜ 性质：Read-only 调研 + 可执行任务书（**本次不改项目代码**）
> 目标项目：`E:/项目工作区/test-xh-dossier`
> 交付物：本文件 `E:/个人知识库/outputs/检索第3-4层落地任务书.md`
>
> **标注约定**：`[代码确认]` = 已读 `E:/项目工作区/test-xh-dossier` 源码/数据库确认；
> `[源码确认]` = 已从项目 GitHub 原始源码文件确认；`[一手文档]` = 已从项目官方 README/论文/官方博客确认；
> `[二手推断]` = 来自第三方解读文章或本人推断，**未经一手资料证实**。

---

## 0. 核心发现（先看结论）

1. **用户的分工判断方向正确，但需要在两处校正**：
   - **④时间检索 = Zep / Graphiti**：确认无误。Graphiti 是 Apache-2.0 开源引擎，实现了严格的**双时态（bi-temporal）**：每条事实边带四个时间戳，`valid_at`/`invalid_at`（真实世界时间 T）+ `created_at`/`expired_at`（系统获知时间 T′）；新事实推翻旧事实时**把旧边的 `invalid_at` 设为新边的 `valid_at`，旧边保留不删**。`[源码确认][一手文档]`
   - **字段名要改口**：用户说的 `t_valid / t_invalid / t_created / t_expired` 是**论文里的数学记号**（论文写作 `t_valid`、`t_invalid`、`t′created`、`t′expired`）。**Graphiti 代码里的真实列名是 `valid_at`、`invalid_at`、`created_at`、`expired_at`**。落地时按代码字段命名，不要按论文记号建表。`[源码确认]`
   - **"Hindsight 只解决③"是工作简化，不是严格事实**：Hindsight 官方 README 明确写 `recall` 有 **4 路并行策略**：Semantic（向量）、Keyword（BM25）、**Graph（Entity/temporal/causal links）**、**Temporal（time range filtering）**。所以 H 本身也有时间路；但它的差异化在③（实体/时间/因果链接），而**可照抄的双时态字段语义与失效规则在 graphiti-core 源码里**。Hindsight README 未公开 node/edge 字段级 schema，也未提及 Zep/Graphiti，因此"H=③、Z=④"是**用户的实用约定 + 本任务的落地分工**，不是官方口径。`[一手文档][二手推断]`

2. **本项目落地的最大现实约束（不粉饰）**：`records.created_at` 是**日期粒度（`YYYY-MM-DD`）**，且每 row 只有一个时间字段。这意味着**真实世界时间 T 和系统获知时间 T′ 在现有数据里是同一个值**，无法区分"这件事什么时候是真的"和"我们什么时候知道的"。Zep 的 `reference_time` / 迟到事实 / 审计回放语义，**在现有数据上只能模拟，不能原样复现**。要补必须改导出格式（见 §5 天花板）。`[代码确认]`

3. **最小可行方案**：不引入图数据库、不接 LLM。用 SQLite 加两张表（`fact_validity`、`entities`+`relations`），把④做成标准区间查询（`AS OF` / overlap），把③做成规则抽取实体的简化图 + 递归 CTE 一跳/两跳遍历。全部可用 pytest 验证。`[本任务设计]`

4. **"Dated Facts: ask what was true when"这句原话未能在一手资料中核实为正式 API 名**。Zep 官方文档确认的等价语义是："point-in-time reasoning — what was the user's plan in January?"、"what was true on a given date"、facts 带 `valid_at/invalid_at/created_at/expired_at`。**语义可信，措辞按二手表述标注**。`[一手文档][二手推断]`

---

## 1. ④时间检索：Zep / Graphiti 的真实实现

### 1.1 项目对应与来源

| 项 | 内容 | 来源 URL |
|---|---|---|
| 论文 | Zep: A Temporal Knowledge Graph Architecture for Agent Memory（2025-01-20，arXiv:2501.13956） | https://arxiv.org/abs/2501.13956 , https://arxiv.org/html/2501.13956v1 |
| 开源引擎 | getzep/graphiti（Apache-2.0），PyPI 包名 `graphiti-core` | https://github.com/getzep/graphiti |
| 边模型源码 | `graphiti_core/edges.py` → `EntityEdge` / `Edge` | https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/edges.py |
| 节点模型源码 | `graphiti_core/nodes.py` → `EntityNode` / `EpisodicNode` / `Node` | https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/nodes.py |
| 搜索源码 | `graphiti_core/search/search.py` → `search()` / `edge_search()` 等 | https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/search/search.py |
| 官方双时态说明 | "How Zep Context Graphs keep two timelines for every fact" | https://www.getzep.com/blog/context-graphs-two-timelines-every-fact/ |
| 官方概念文档 | Zep Key Concepts（Fact Invalidation / Memory Context / graph.search） | https://help.getzep.com/v2/concepts |
| 官方 Context Types | Facts / Entities / Episodes / Summaries，`client.graph.search` 形态 | https://blog.getzep.com/zep-context-types |
| 官方 TKG 页 | 四时间戳表、point-in-time query | https://www.getzep.com/ai-agents/temporal-knowledge-graph/ |
| 抽取时序博客 | "Beyond Static Graphs"（日期抽取、reference timestamp） | https://zep-memory-for-ai.ghost.io/beyond-static-knowledge-graphs |

### 1.2 双时态机制（这是④要抄的核心）

论文原文：*"Zep implements a bi-temporal model, where timeline T represents the chronological ordering of events, and timeline T′ represents the transactional order of Zep's data ingestion."*
*"the system tracks four timestamps: t′created and t′expired ∈ T′ monitor when facts are created or invalidated in the system, while t_valid and t_invalid ∈ T track the temporal range during which facts held true."* `[一手文档]`

| 时间轴 | 代码字段（真实列名） | 论文记号 | 语义 |
|---|---|---|---|
| T（世界时间 / valid time） | `valid_at` | `t_valid` | 事实在世界里开始为真 |
| T（世界时间 / valid time） | `invalid_at` | `t_invalid` | 事实停止为真 |
| T′（系统时间 / transaction time） | `created_at` | `t′created` | 系统获知该事实 |
| T′（系统时间 / transaction time） | `expired_at` | `t′expired` | 系统判定该事实被取代 |

**失效规则（论文原文）**：*"When the system identifies temporally overlapping contradictions, it invalidates the affected edges by setting their `t_invalid` to the `t_valid` of the invalidating edge."* `[一手文档]`
**代码注释确认**：`expired_at` 的 docstring 是 *"datetime of when Graphiti marked the edge as invalidated (transaction time); use invalid_at to find when the fact stopped being true"* — 即**两条轴分别用不同的字段回答不同的问题**。`[源码确认]`

**AS OF 语义**（把它化为 SQL 后的样子，Graphiti 原实现跑在 Neo4j Cypher 上）：
```sql
-- 世界时间视角："在 2026-03-01，这件事是真的吗？"
WHERE valid_at <= :as_of AND (invalid_at IS NULL OR :as_of < invalid_at)

-- 系统时间视角："在 2026-03-01，系统当时知道什么？"（审计/事故复盘）
WHERE created_at <= :as_of AND (expired_at IS NULL OR :as_of < expired_at)
```
Zep 官方给出的查询侧表述：*"Point-in-time reasoning. 'What was the user's plan in January?' is answerable — not only 'what is it now?'"*；`client.graph.search(user_id=..., query=..., limit=5)` 返回带有效期窗口与 provenance 的 facts。`[一手文档]`

### 1.3 数据结构（源码逐字段确认）

`EntityEdge`（`graphiti_core/edges.py`）字段：`uuid`、`group_id`、`source_node_uuid`、`target_node_uuid`、`created_at`（继承自基类 `Edge`）、`name`（关系名）、`fact`（事实文本）、`fact_embedding`、`episodes`（来源 episode id 列表 = provenance）、`expired_at`、`valid_at`、`invalid_at`、`reference_time`、`attributes`。`[源码确认]`

`EntityNode`（继承 `Node`）字段：`uuid`、`name`、`group_id`、`labels`、`created_at`、`name_embedding`、`summary`、`attributes`。
`EpisodicNode`（继承 `Node`）字段：`uuid`、`name`、`group_id`、`labels`、`created_at`、`source`（`EpisodeType`: message/json/text/fact_triple）、`source_description`、`content`、`valid_at`（原始文档创建时间）、`entity_edges`、`episode_metadata`。**注意：当前 `EpisodicNode` 源码里没有 `reference_time` 字段，`reference_time` 是 `add_episode()` 的入参；论文写作 `t_ref`。** `[源码确认]`

论文的三层图：`Episode Subgraph G_e`（原始输入）、`Semantic Entity Subgraph G_s`（实体+事实边）、`Community Subgraph G_c`（强连通实体簇+摘要）。`[一手文档]`

### 1.4 检索 API 形态（避免写错方法名）

`graphiti_core/search/search.py` 里的真实公开函数是模块级 `async def`，**不是** `Graphiti.search()` / `search_edges()` / `recall()`：
`search(clients, query, group_ids, config: SearchConfig, search_filter: SearchFilters, center_node_uuid=None, bfs_origin_node_uuids=None, query_vector=None, driver=None) -> SearchResults`；下层 `edge_search()` / `node_search()` / `episode_search()` / `community_search()`，数量参数是 `limit` 而非 `num_results`。`[源码确认]`
论文侧三种检索函数：cosine semantic similarity（搜 `fact` 字段）、Okapi BM25、BFS（n-hop 邻域 + 可按近期 episode 做 seed）。`[一手文档]`

### 1.5 graphiti-core 最小可用需要什么（诚实清单）

- Python 包：`graphiti-core[neo4j|falkordb|neptune]` `[一手文档]`
- 图数据库（**必选其一**）：Neo4j 5.26、FalkorDB 1.1.2、Amazon Neptune + OpenSearch Serverless（full-text 后端）。**SQLite 不在支持列表里**。`[一手文档]`
- LLM：默认 OpenAI；强依赖 **Structured Output**（实体/边抽取与去重），README 明确警告小模型会 extraction failure；支持 Azure/Anthropic/Gemini/Groq/Ollama OpenAI-compatible（`OpenAIGenericClient`）。`[一手文档]`
- Embedding 模型 + 可选 cross-encoder reranker；环境变量 `OPENAI_API_KEY`、`SEMAPHORE_LIMIT`（默认 10，控 429）。`[一手文档]`
- **结论：完整 graphiti-core = LLM 费用 + 图数据库运维 + 网络调用，不是"pip 一下就能在 xh-dossier 里跑"的东西。** 这属于 §5 天花板。

---

## 2. ③图检索：Hindsight 对照（用户说 H 只解决③）

来源：https://github.com/vectorize-io/hindsight `[一手文档]`

- 定位：*"agent memory system built to create smarter agents that learn over time"*；记忆类型 **World facts / Experiences / Observations / Mental models**，存于隔离的 **banks**。
- `retain(...)` 用 LLM 抽取 *"key facts, temporal data, entities, and relationships"* 并归一化成 *"canonical entities, time series, and search indexes"*。
- `recall(...)` **四路并行**：`Semantic`（向量）、`Keyword`（BM25）、**`Graph`（Entity/temporal/causal links）**、`Temporal`（time range filtering）；后用 reciprocal rank fusion + cross-encoder rerank + token 裁剪。
- 图检索的原文术语就是 **"Entity/temporal/causal links"**；**README 未给出 node/edge 字段级 schema，也未出现 Zep/Graphiti 字样**。
- 运行形态：`pip install hindsight-api / hindsight-client`，服务需 PostgreSQL+pgvector 或 Oracle AI Database 23ai（或 embedded pg0）；自带 `hs-decide-1-flash`（0.8B, Apache-2.0）、`hs-rerank-1`（114M, MIT）、`hs-embed-1`（112M, MIT）。

**分工差异的诚实表述**：
- 用户"H 只解决③"应理解为**落地选型约定**：H 的差异化在③（实体/时间/因果链接 + observations/mental models 的整合），④的可复刻基准要去 Zep/Graphiti 找。
- 严格说 H 也做④（有 Temporal 路与 time series），但它**没有公开四时间戳边模型**，且是"服务+专有小模型+PG"的交付形态；graphiti-core 是源码可见的 Apache-2.0 库。**因此本任务书以 graphiti-core 为字段语义蓝本、以 Hindsight 为③的参考愿景（实体/因果链接 + 四路召回融合），不把 H 当作可直接抄表结构的对象。**
- 来源中还有一条第三方解读可作为背景但**不当作一手证据**：https://memu.pro/blog/zep-temporal-knowledge-graph-agent-memory （Graphiti/Zep/Batch GraphRAG 对比表）；https://graphwiz.ai/content/knowledge-graphs/agent-memory-time-travel-benchmark （AS-OF 的 Cypher 示例，用 `t_valid/t_invalid` 记号，非代码字段）。

---

## 3. 现有代码事实基线 `[代码确认]`

### 3.1 `scripts/01_clean_and_index.py`

- `clean_and_index(raw_dir, db_path) -> dict`：建 `records` 表 + `records_fts` 虚拟表（`tokenize='trigram'`）。
- 表结构（`01_clean_and_index.py:220-229`）：
  ```sql
  CREATE TABLE records (
      rec_id TEXT PRIMARY KEY,
      source_file TEXT NOT NULL,
      created_at TEXT NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      md5 TEXT NOT NULL UNIQUE
  );
  CREATE VIRTUAL TABLE records_fts USING fts5(rec_id UNINDEXED, content, tokenize='trigram');
  ```
- `rec_id` 形如 `REC-0001`；md5 是对 `content` 全文做 hash，用于全库去重（同文只留第一条）。
- `search_keyword(db_path, query, limit=20)`：`>=3` 字符走 FTS5 MATCH，`<3` 字符走转义 LIKE 兜底（这是①的现状）。
- **AfterChat 真实导出解析**（`01_clean_and_index.py:141-170`）：识别 `## Conversation` + `🧑‍💻 User/🤖 Assistant`，从 `**Time:** YYYY-MM-DD` 取 `file_ts` 作为该次会话所有 turn 的 `created_at`；legacy 分支按 section 内日期或 file_ts 取值。
- **实测现有库**：`work/real_index.db` 有 **729 条** records，`created_at` 样例为 `2026-11-07 / 2026-10-05 / 2026-11-18 / 2026-09-19 ...`，**均为 `YYYY-MM-DD` 日期字符串，无时分秒，且无 unknown**（与用户"已修复"一致）。`work/unified_index.db` 10 条，同格式。

### 3.2 `scripts/02_four_way_match.py`

- `run_four_way_pipeline(db_path, keywords, use_fastembed=False, cluster_threshold=None, pattern_threshold=0.16) -> dict`：
  - 从 `records` 读 `rec_id, source_file, created_at, role, content`；
  - Way1 关键词（`search_keyword`）；Way2 向量（TF-IDF 字符 n-gram，可选 `fastembed` BAAI/bge-small-zh-v1.5，**仅候选召回**）；Way3 `mean_center_and_normalize` + `cluster_vectors` 贪心密度聚类；Way4 `DEFAULT_PATTERNS` 模式种子 + `apply_guardrails` 主宾倒置/否定拦截。
  - `render_backfill_markdown(report) -> str` 输出 `[REC-xxxx | 日期]` 可追溯报告。
- 现状：**①已实现，②已实现（仅候选召回），③④未实现**。四路里的"四路"是关键词/向量/聚类/模式，**不是**用户框架的①-④。`[代码确认]`
- 可复用资产：`apply_guardrails(content, pattern_kind)` 用于③抽取的否定/主宾误报拦截；`chunk_text` 用于长文本；`cosine_sim` / `_l2_normalize_dict` 用于简化图边打分。
- 测试基线：`tests/test_pipeline.py` 现有 9 个测试（pytest），新增测试不得破坏它。

---

## 4. 最小可行实现方案（SQLite + SQL，零外部依赖）

**设计原则**：④先做"区间代数"，③先做"规则抽取的实体-关系图"。**不改 `01/02` 任何一行**，新脚本通过 `import_module` 复用（`02_four_way_match.py:18-23` 已有此模式）。所有新表与 `records` 用 `rec_id` 关联，保持 provenance。

### 4.1 ④时间检索：新文件 `scripts/05_temporal_index.py`

新建表（**字段故意对齐 graphiti-core 的真实列名，便于日后迁移**）：
```sql
CREATE TABLE IF NOT EXISTS fact_validity (
    fact_id        TEXT PRIMARY KEY,             -- = records.rec_id（最小版一行一事实）
    valid_from     TEXT NOT NULL,                -- ← 论文 t_valid / 代码 valid_at
    valid_to       TEXT,                         -- ← t_invalid / invalid_at；NULL=仍为真
    created_at     TEXT NOT NULL,                -- ← t'_created / created_at（系统获知）
    expired_at     TEXT,                         -- ← t'_expired / expired_at
    superseded_by  TEXT,                         -- 失效它的新 fact_id
    source_rec_id  TEXT NOT NULL,                -- provenance → records.rec_id
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_fv_valid ON fact_validity(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_fv_created ON fact_validity(created_at, expired_at);
```
> 日期统一存 `YYYY-MM-DD` 字符串（SQLite 字典序可比）；`NULL` 表示开放区间，与 Graphiti 的 nullable `invalid_at/expired_at` 一致。

函数签名（**任务书指定的对外接口**）：
```python
def normalize_date(value: str) -> str | None: ...
def ensure_temporal_schema(db_path: pathlib.Path) -> None: ...
def backfill_from_records(db_path: pathlib.Path) -> dict[str, int]: ...
def invalidate_fact(
    db_path: pathlib.Path,
    old_fact_id: str,
    new_fact_id: str,
    *,
    valid_to: str | None = None,     # 默认取 new_fact.valid_from（Graphiti 规则）
    expired_at: str | None = None,   # 默认取当天 UTC 日期
) -> dict: ...
def query_as_of(
    db_path: pathlib.Path,
    as_of: str,
    *,
    clock: str = "valid",            # "valid"(T) | "transaction"(T')
    limit: int = 50,
) -> list[dict]: ...
def query_time_range(
    db_path: pathlib.Path,
    start: str,
    end: str,
    *,
    clock: str = "valid",
    limit: int = 100,
) -> list[dict]: ...
def render_temporal_markdown(rows: list[dict], *, as_of: str, clock: str) -> str: ...
def main() -> int: ...   # --db --action backfill|as-of|range --as-of --start --end --clock
```
关键 SQL 语义：
- `clock="valid"`：`valid_from <= :as_of AND (valid_to IS NULL OR valid_to > :as_of)`
- `clock="transaction"`：`created_at <= :as_of AND (expired_at IS NULL OR expired_at > :as_of)`
- `query_time_range`：overlap：`valid_from <= :end AND (valid_to IS NULL OR valid_to >= :start)`
- `invalidate_fact` **只 UPDATE，绝不 DELETE**；同时写 `superseded_by`、`expired_at`。
- `backfill_from_records`：因现有数据只有一个日期，**`valid_from = created_at = records.created_at`**，`valid_to/expired_at` 留 NULL；日期无法解析（如 `unknown`）的 row 计入 `skipped`，不写脏数据。

**降级诚实点**：因为 T 与 T′ 同值，`clock="transaction"` 的"当时知道什么"在 backfill 后的行为≈valid clock，只有经过 `invalidate_fact` 写出不同的 `expired_at` 后才会分化。这是数据限制，不是代码 bug，必须在输出 markdown 里明说。

### 4.2 ③图检索：新文件 `scripts/06_graph_index.py`

新建表：
```sql
CREATE TABLE IF NOT EXISTS entities (
    entity_id      TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type    TEXT NOT NULL DEFAULT 'unknown',
    aliases        TEXT NOT NULL DEFAULT '[]',   -- JSON array
    first_seen     TEXT,
    UNIQUE(canonical_name, entity_type)
);
CREATE TABLE IF NOT EXISTS relations (
    rel_id         TEXT PRIMARY KEY,
    src_entity_id  TEXT NOT NULL,                -- → entities.entity_id
    dst_entity_id  TEXT NOT NULL,
    predicate      TEXT NOT NULL,                -- WORKS_AT / LIVES_IN / LIKES / MENTIONS / ...
    fact_text      TEXT NOT NULL,
    rec_id         TEXT NOT NULL,                -- provenance → records.rec_id
    valid_from     TEXT,
    valid_to       TEXT,
    created_at     TEXT NOT NULL,
    expired_at     TEXT,
    confidence     REAL NOT NULL DEFAULT 1.0,
    extractor      TEXT NOT NULL DEFAULT 'rule', -- 'rule'（本版）| 'llm'（未来）
    UNIQUE(src_entity_id, dst_entity_id, predicate, rec_id)
);
```
函数签名：
```python
def ensure_graph_schema(db_path: pathlib.Path) -> None: ...
def extract_entities(content: str, *, lexicon: Iterable[str] = ()) -> list[dict]: ...
def extract_relations(content: str, entities: list[dict]) -> list[dict]: ...
def build_graph(db_path: pathlib.Path, *, lexicon: Iterable[str] = ()) -> dict[str, int]: ...
def graph_neighbors(
    db_path: pathlib.Path,
    entity_name: str,
    *,
    hops: int = 1,
    as_of: str | None = None,
    limit: int = 50,
) -> list[dict]: ...
def render_graph_markdown(rows: list[dict], *, entity_name: str) -> str: ...
def main() -> int: ...   # --db --action build|neighbors --entity --hops --as-of
```
实现约束（**决定它只是"简化版"**）：
- `extract_entities` 不做真 NER：只做 ①用户传入 `lexicon`（实体白名单）精确匹配；②中文引号/书名号 `「」《》""` 内名词；③显式 "我/本人" 归一为固定结点。命中即生成 entity，未命中就跳过。
- `extract_relations` 用有限正则模板（`在…工作/任职`、`住在/搬到`、`负责`、`喜欢/偏好`、`把…改成…` 等），并把 `02_four_way_match.apply_guardrails` 接进来：`NEGATION_MARKERS` 命中则不产边（避免"先不要…"被当成事实）。
- `graph_neighbors` 用 SQLite **递归 CTE** 做 1~2 跳 BFS；`as_of` 传入时叠加 §4.1 的 valid 窗口过滤；每条返回必须带 `rec_id` 可回溯原文。
- 实体/关系的时间字段来自 `records.created_at`（同样 T=T′ 降级）。

### 4.3 接入方式（不改旧文件）

```
python scripts/05_temporal_index.py --db work/real_index.db --action backfill
python scripts/05_temporal_index.py --db work/real_index.db --action as-of --as-of 2026-05-01 --clock valid
python scripts/06_graph_index.py --db work/real_index.db --action build --lexicon <可选>
python scripts/06_graph_index.py --db work/real_index.db --action neighbors --entity "<某实体>" --hops 1 --as-of 2026-10-01
```
新测试文件：`tests/test_temporal_graph.py`（不改 `tests/test_pipeline.py`）。

---

## 5. 验收标准（pytest 可验证）

`tests/test_temporal_graph.py` 必须包含且通过以下断言（本任务书的验收线）：

| # | 测试函数（建议名） | 断言要点 | 对应能力 |
|---|---|---|---|
| 1 | `test_normalize_date_handles_real_and_unknown` | `normalize_date("2026-11-18")=="2026-11-18"`；`"unknown"→None`；ISO 时间戳可截取日期 | 数据边界 |
| 2 | `test_backfill_maps_created_at_both_clocks` | backfill 后 `valid_from==created_at==records.created_at`；unknown 行 `skipped>=1` | ④建表 |
| 3 | `test_as_of_returns_old_fact_and_excludes_new` | 造两条（`2026-01-10` A、`2026-06-01` B），`invalidate_fact(r1,r2)`；`query_as_of("2026-03-01",clock="valid")` 只含 r1；`"2026-07-01"` 只含 r2 | **AS OF 核心** |
| 4 | `test_invalidation_never_deletes_history` | 失效后 `SELECT count(*) FROM fact_validity` 仍为 2；旧行 `valid_to=="2026-06-01"`（=新行 `valid_from`）、`expired_at` 非空、`superseded_by==r2` | Graphiti 规则 |
| 5 | `test_transaction_clock_differs_after_invalidation` | `query_as_of("2026-05-01",clock="transaction")` 含 r1 不含 r2（r2.created_at 晚于 as-of） | 双时钟分化 |
| 6 | `test_time_range_overlap_includes_open_interval` | `query_time_range("2026-03-01","2026-08-01")` 同时含两条开放/闭合区间 | ④区间检索 |
| 7 | `test_out_of_order_fact_is_kept` | 手工写入 `valid_from < created_at` 的行；valid clock 能查到、transaction clock 在 `created_at` 之前查不到 | 迟到事实（模拟） |
| 8 | `test_graph_extraction_respects_negation_guardrail` | `"先不要…改成…"` 经 `extract_relations` 产出 0 条边 | ③防误报 |
| 9 | `test_graph_neighbors_one_hop_and_provenance` | build 后 `graph_neighbors(name,hops=1)` 返回 ≥1 条，且每条 `rec_id` 都能在 `records` 命中 | ③可追溯 |
| 10 | `test_as_of_filter_on_graph_edges` | 传入 `as_of` 早于边 `valid_from` 时返回空 | ③④联动 |
| 11 | `test_no_regression_existing_pipeline` | `pytest -q tests/test_pipeline.py` 全绿（9 passed） | 不破坏旧功能 |

**整体验收命令**：
```bash
cd "E:/项目工作区/test-xh-dossier"
python -m pytest -q tests/test_temporal_graph.py tests/test_pipeline.py
```
通过标准：全部 passed；且对 `work/real_index.db` 执行 `--action backfill` 后 `fact_validity` 行数 == `records` 中可解析日期的行数 ≤ 729。

---

## 6. 能落地 vs 天花板（不粉饰）

### 6.1 真能落地（本任务书范围，SQLite 即可）

- ④ **AS OF 事实回溯（valid 窗口）**：区间查询是纯 SQL，729 条数据零压力。**能回答"某日期之前生效、之后失效的记录"**。
- ④ **失效不删除**：`UPDATE valid_to/expired_at` 保留历史 + `superseded_by` 指向新事实，审计链完整。
- ④ **双时钟的"骨架"**：字段齐全，只要未来数据提供两种时间，SQL 不用改就能分化。
- ④ **时间区间检索 / 时间轴切片**：overlap 查询、按 `source_file` + 日期分组。
- ③ **白名单实体 + 正则关系的简化图**：一跳/两跳邻域、带 `rec_id` provenance；复用现有 guardrail 拦截否定误报。
- ③ **四路召回融合的"形态"**：可以用现有 `keyword_hits`、`clusters`、`pattern_hits` + 新的 temporal/graph 结果做 RRF 合并（**但这是输出层拼装，不是 Graphiti 级重排**）。

### 6.2 天花板 / 必须外部依赖（**本任务书不承诺**）

| 目标 | 缺什么 | 为什么现在做不到 |
|---|---|---|
| 真·双时态（T≠T′）、迟到事实、事故回放 | 导出数据需携带**事件发生时间**与**入库时间**两个字段，或 `reference_time` | 现有 `records` 只有 `created_at`（日期粒度），T 与 T′ 物理上是同一列 `[代码确认]` |
| 时分秒级 "as of 14:32" | 导出格式需保留时间部分；当前 AfterChat 解析只取 `YYYY-MM-DD`（`01:150`） | 正则 `\*\*Time:\*\*\s*(\d{4}-\d{2}-\d{2})` 主动丢弃了时分秒 `[代码确认]` |
| LLM 实体/关系抽取、实体消歧、矛盾裁决、community 摘要 | OpenAI-compatible LLM（**需 Structured Output**）+ 图库 | graphiti-core README 明确强依赖；小模型会 extraction failure `[一手文档]` |
| 完整 Graphiti 语义（episode 图、fact_embedding、BM25、BFS、node_distance rerank、`graphiti-core` API） | `graphiti-core` + Neo4j 5.26 / FalkorDB / Neptune + embedding + reranker | **SQLite 不在官方支持列表里** `[一手文档]` |
| Hindsight 级 4 路 recall + observations/mental models/pages | `hindsight-api` 服务 + PostgreSQL/pgvector（或 pg0）+ 其 decision/rerank/embed 模型 | 服务化交付，README 无字段级 schema 可抄 `[一手文档]` |
| 高召回中文 NER / 开放关系抽取 | 中文 NER 模型或 LLM | 规则版只能覆盖白名单与固定句式，**召回率会很低**，不要拿它当"真图检索" |
| 时间表达式理解（"上个月""两年前""上周四"） | 需要按 `reference_time` 做相对时间解析的 LLM prompt | Graphiti 是在写入时由 LLM 解析的 `[一手文档]`；本项目无此能力 |

### 6.3 数据侧两个必须写进报告的坑 `[代码确认]`

1. **MD5 全内容去重**：同一句话在不同日期重复出现，只有第一次进库 → 事务时间证据被抹掉。要做"某说法何时反复出现"必须先改去重键（如 `md5(content, created_at)`），本次不改。
2. **`created_at` 是会话级而非 turn 级**：`_extract_from_text` 的 real_export 分支把同一文件里所有 turn 都赋同一个 `file_ts`，单次会话内多天的事实无法区分。

---

## 7. 事实 / 推断对照表

| 结论 | 标注 | 依据 |
|---|---|---|
| Graphiti 四时间戳为 `valid_at/invalid_at/created_at/expired_at` | `[源码确认]` | `graphiti_core/edges.py` 的 `EntityEdge` |
| 论文记号是 `t_valid/t_invalid/t′created/t′expired` | `[一手文档]` | arXiv HTML §2.2.3、Appendix 6.1.5 |
| 失效=旧边 `invalid_at` 置为新边 `valid_at`，不删除 | `[一手文档]` | 论文原文 + README "invalidated, not deleted" |
| `t_invalid` 是用户写法、非代码字段 | `[源码确认]` | 同上对照 |
| Zep 支持 point-in-time / "what was true on a given date" | `[一手文档]` | getzep.com 官方 TKG 页与官方博客 |
| "Dated Facts: ask what was true when" 是正式 API 名 | `[二手推断]` | **未在一手资料核实**；只核实了等价语义 |
| Hindsight `recall` 四路含 Graph + Temporal | `[一手文档]` | GitHub README |
| "Hindsight 只解决③" | `[二手推断]` | 用户工作约定；README 有 Temporal 路，但无公开四时间戳 schema |
| Hindsight vs Zep 的官方分工说法 | `[二手推断]` | Hindsight README 未提 Zep/Graphiti |
| graphiti-core 需图库 + LLM structured output，SQLite 不支持 | `[一手文档]` | Graphiti README Requirements |
| 本项目 `records` 字段、`created_at` 为 `YYYY-MM-DD`、729 条 | `[代码确认]` | `01_clean_and_index.py:220-229` + 实查 `work/real_index.db` |
| 四路匹配现状不含③④（是关键词/向量/聚类/模式） | `[代码确认]` | `02_four_way_match.py:215-300`、`render_backfill_markdown` |
| SQLite + SQL 的最小方案与验收用例 | `[本任务设计]` | 尚未实现，需按 §4/§5 执行 |

---

## 8. 建议执行顺序（后续会话用）

1. **T1** 新建 `scripts/05_temporal_index.py`（§4.1），只做 backfill + as-of + range + invalidate；先写 §5 的 #1~#7 测试，跑绿。
2. **T2** 新建 `scripts/06_graph_index.py`（§4.2），白名单 + 正则边 + 递归 CTE；补 §5 #8~#10 测试，跑绿。
3. **T3** 对 `work/real_index.db` 做一次真实 backfill/build，把输出与 `tests/test_pipeline.py` 一起回归（#11），**不写回 `records` 表**。
4. **T4**（可选，仍需评估）在输出 markdown 里做 RRF 融合展示；不引入 LLM、不引入图库。
5. **T5**（需用户另行决策，超出本任务书）若要真·双时态，先改导出器保留时分秒与 `reference_time`，再评估自建 Neo4j/FalkorDB + graphiti-core 的成本。

---

## 9. 来源 URL 汇总

**一手（已核对）**
- https://arxiv.org/abs/2501.13956 ；https://arxiv.org/html/2501.13956v1
- https://github.com/getzep/graphiti
- https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/edges.py
- https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/nodes.py
- https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/search/search.py
- https://www.getzep.com/blog/context-graphs-two-timelines-every-fact/
- https://www.getzep.com/ai-agents/temporal-knowledge-graph/
- https://help.getzep.com/v2/concepts
- https://blog.getzep.com/zep-context-types
- https://zep-memory-for-ai.ghost.io/beyond-static-knowledge-graphs
- https://github.com/vectorize-io/hindsight

**二手（仅背景，未当证据）**
- https://memu.pro/blog/zep-temporal-knowledge-graph-agent-memory
- https://graphwiz.ai/content/knowledge-graphs/agent-memory-time-travel-benchmark
- https://aiagentmemory.org/articles/temporal-reasoning-ai-memory
- https://www.memoryplugin.com/wiki/temporal-memory.html
- https://www.memoryatlas.dev/articles/zep-deep-dive
- https://tianpan.co/zh/blog/2026-07-02-your-agents-memory-needs-two-clocks

**本地代码（已读）**
- `E:/项目工作区/test-xh-dossier/scripts/01_clean_and_index.py`
- `E:/项目工作区/test-xh-dossier/scripts/02_four_way_match.py`
- `E:/项目工作区/test-xh-dossier/tests/test_pipeline.py`
- `E:/项目工作区/test-xh-dossier/work/real_index.db`（只读查询）
