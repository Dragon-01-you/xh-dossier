# 07 · 真实语料四路全 0：用户反复纠正 + 明确要求 TDD，仍挖不出任何候选

Status: ready-for-human
Type: bug
Priority: P0
Step: S6.1 / S6.5

## 现象

真实会话《Build Dirac Sea supercar game》（6 条消息，3 user / 3 assistant）中，用户两次明确表达不满并给出方法要求：

- 第 3 条：「你自己根本不像我给你的这个图片」「我感觉这里不太像」
- 第 5 条：「我觉得有些东西还是没太好」「你得先去测试对比」「建议你在开始做之前，先进行监测，使用 TDD」「只有一次机会……必须先把它做好测试」

跑 `02`：

```text
FOUR_WAY_OK records=6 clusters=3
Way 1 记错/验收/拖延/口音：全部 0
Way 4 三个模式：全部 0 条通过
```

即：**产品主打的两个信号（反复纠正、先验收再动手）都真实存在，四路匹配一条也没抓到**，但程序仍打印 `FOUR_WAY_OK`、exit 0。

## 根因

`DEFAULT_PATTERNS` 的 9 个种子句是作者个人经历的措辞（「你还是没理解我」「开工先定验收标准」等）。TF-IDF 字符 n-gram 相似度对同义改写不敏感，`pattern_threshold=0.16` 下全部落选。真实用户不会用作者的措辞说话。

## 证据

- 输入：`/tmp/xh-run/raw-real-2/Dirac-Sea-supercar.md`（SHA256 见 spec.md）
- 输出：`/tmp/xh-run/work/real2-bf.md`
- 对照：mock 语料（照种子句写）能命中；真实语料 0 命中

## 期望

- 模式不应由硬编码种子句驱动，至少应支持从用户 Stage 1 的 `02-核心判断准则.md` / `04-正反例避坑账.md` 自动抽取种子；
- 增加结构化信号（同一话题下连续 user 轮出现否定/修正词，且紧跟 assistant 回复）作为候选来源，不依赖措辞；
- 0 候选时输出 `FOUR_WAY_NO_CANDIDATES` + 非零，不得 `FOUR_WAY_OK`。

## 最小修复

1. `--patterns <json>` 允许外部种子；
2. 新增 `--patterns-from-kit <dir>`，从用户自己的 02/04 抽句；
3. 加一个真实语料 fixture（本文件）进 CI，断言至少命中 1 条「纠正」候选；
4. 0 候选 → `FOUR_WAY_NO_CANDIDATES`。

## 修复（2026-11-22）

- 新增结构化规则「用户明确纠正或否定」，只作用于 user 轮，不依赖种子句。
- 新增 `--patterns <json>` 与 `--patterns-from-kit <dir>`（从用户自己的 02/04 抽种子）。
- 0 候选 → `FOUR_WAY_NO_CANDIDATES` + exit 2，不再打印 `FOUR_WAY_OK`。
- 回归：`test_user_correction_is_detected_without_seed_wording`、`test_zero_candidates_exits_nonzero`、`test_patterns_from_kit`
- 复验：真实会话修复前 0 候选 → 修复后 `candidates=2`（REC-0003 / REC-0005）。
