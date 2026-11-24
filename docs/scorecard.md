# 评分卡 v1（issue #96 / E6-T1）

结构校验（六份存在、≥80 字、空话 / 日期 / PII / 占位符 / 出处三件套）只回答“能不能读”，
不回答“够不够好”。本评分卡在结构合格之外给出四条**可判定**指标，每条带数值、阈值与不达标时的具体缺口。

## 1. 指标与默认阈值

| 指标 | 口径 | 默认阈值 | 不达标时输出 |
|---|---|---|---|
| `coverage` 覆盖度 | 6 个槽位（身份 / 主线 / 准则 / 规则 / 正例 / 反例）中，含至少一条**带原文+出处**条目的槽位占比 | ≥ 0.80（5/6） | 列出缺哪些槽位 |
| `answerable_questions` 三问可答性 | 盲测三问（身份是谁 / 当前主线 / 判断准则）能从六份直接答出的比例 | ≥ 2/3 | 列出未答的问题 |
| `citation_accuracy` 引用准确率 | 可在 kit 内解析到出处行的带出处条目 / 全部带出处条目；`noise_rate = 1 - accuracy` | ≥ 0.90 | 列出不可追溯的文件与原因码 |
| `mainline_unique` 主线唯一性 | raw B 级主线候选是否 ≤ 1 条（A 级访谈主线是基准答案，不计入竞争候选） | 必须为 1（唯一） | 当前主线候选条数；其余应进历史区 |

槽位认定只认真实条目：空提示句、机器归纳填充句、`[待确认]` 占位都不算已覆盖。

## 2. 命令

```powershell
# 默认：结构校验 + 评分卡（评分卡仅提示，不翻转 VALIDATE_OK）
python -X utf8 scripts/xh.py validate --kit work/kit --strict

# 阈值不达标时直接判 FAIL（把评分卡接进门禁）
python -X utf8 scripts/xh.py validate --kit work/kit --strict --enforce-score

# 跳过评分卡（只看结构）
python -X utf8 scripts/xh.py validate --kit work/kit --no-scorecard
```

脚本入口：`scripts/03_validate_kit.py` 的 `score_kit()` / `format_scorecard()`；
阈值常量 `SCORE_THRESHOLDS`，调用方可传入 `thresholds` 覆盖。

## 3. 阈值裁定边界

- 默认阈值是起点，**最终 cut line 由用户裁定**；A 级条目数下限、误判率上限、主线收敛条数都可调。
- “本人亲历占比”这类主观指标无法纯脚本判定，评分卡不冒充能测；它只清点可机器核对的部分。
- 评分卡通过 ≠ 可以交付：仍需走 #90 的本人复核回执（`review --confirm`）与 #98 的独立 Agent 三问盲测。

## 4. 与外部标准的关系

本评分卡的指标清单来自仓内流程需要；外部顶尖档案 / 交接做法的对照与信源候选见
`docs/standard-v1.md`（#97）。标准 v1 生效前，不拿自家六份当尺子。
