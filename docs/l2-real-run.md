# 二次回流真实运行记录（2026-11-25）

> 结论：**这次是真实的跨对话差集：按 `source_file` 去重，必须 ≥2 个不同对话才入选。** 但主题抽取仍是固定 6 类 cue 规则，不是开放式聚类——跨对话门槛是真的，规则扫描也是真的。729 条真实库跑出 6 条主题候选，写入 `[待确认]` 区，结构校验 `VALIDATE_OK`；但**没有本人签字，不能算“二次回流已完成”**。

## 1. 运行命令

```bash
python -X utf8 scripts/05b_l2_theme.py \
  --profiles work/real/kit \
  --first-pass work/real/backfill_candidates.md \
  --db work/real/unified_index.db \
  --out work/real/l2_theme
```

```text
L2_THEME_OK records=729 personal_records=346 candidates=6 dropped=222
themes=["L2-1001:hard_rule", "L2-1002:recurring_mistake", "L2-1003:hard_rule",
        "L2-1004:hard_rule", "L2-1005:hard_rule", "L2-1006:hard_rule"]
```

## 2. 六条候选

| ID | 主题 | 跨对话 docs | 建议位置 | 状态 |
|---|---|---:|---|---|
| L2-1001 | 一手资料 / 真实比对 | 5 | `03` 硬规则 | `[待确认]` |
| L2-1002 | 拆解必须落到成品 | 4 | `04` 反例 | `[待确认]` |
| L2-1003 | 本地跑不动就走 API/云端 | 3 | `03` 硬规则 | `[待确认]` |
| L2-1004 | 3D 资产只做参考建模 / 多视图 | 2 | `03` 硬规则 | `[待确认]` |
| L2-1005 | 解释必须说人话 | 6 | `03` 黑话 | `[待确认]` |
| L2-1006 | 必须用真实项目验证 | 2 | `03` 硬规则 | `[待确认]` |

原文摘录（各选一条）：

- `L2-1001`：> 我想看的是真正的一手原型，而不是你看别人官网上的东西
- `L2-1002`：> 你这成品没做出来，我就让你的成品去跟它对应校验啊
- `L2-1003`：> 因为在本地我跑不了这么大的模型……太卡了，我可以接入对应的 API
- `L2-1004`：> 把它拆分为不同的资产，并制作成多视图
- `L2-1005`：> 语言尽量通俗，不要堆砌资料
- `L2-1006`：> 如果做出来且测试可行，再通知我

> 代表 `REC` 编号会因两份 729 条库副本的编号差异而略有不同；主题、docs 数和摘录保持一致。最终签字时以同一份签名库为准。

## 3. 写入待确认区

加固后的 `08` 要求目标档案末尾有显式锚点 `[XH-L2-PENDING-END]`；缺锚点会安全失败，不再盲追加到文件尾。

```bash
python -X utf8 scripts/08_l2_apply.py \
  --kit work/real/kit_anchor \
  --l2 work/real/l2_theme \
  --out work/real/kit_l2_next_v2
```

```text
L2_APPLY applied=6 skipped_existing=0 question_skipped=0 \
  kit=.../kit_l2_next_v2 validate=OK scorecard=FAIL
SCORECARD_FAIL: mainline_unique 0.00 ≥ 1.00 — 主线候选 3 条
```

加固后复跑：`03` 4,522 bytes、`04` 2,563 bytes（含锚点行）；**`02` 仍是 605 bytes（含锚点），没有变厚**，因为这次 6 条主题都落在硬规则/反例，不是判断准则。旧版 `kit_l2_next`（4,536 / 2,569）保留作历史对照。

## 4. 评分卡（结构合格，但仍不可发布）

```text
VALIDATE_OK
[PASS] coverage: 0.83 ≥ 0.80 — 缺 principle
[PASS] answerable_questions: 0.67 ≥ 0.67 — 未答：判断准则
[PASS] citation_accuracy: 1.00 ≥ 0.90 — 引用 21/21 可追溯
[FAIL] mainline_unique: 0.00 ≥ 1.00 — 主线候选 3 条
SEMANTIC_REVIEW: 15 条语义提示
```

## 5. 这次到底解决了什么

- 解决了“`05_deep_backfill.py` 在 729 条上 strict/broad 都是 0 条”的假阴性：旧脚本有跨文档短语统计，但只用于排序/证据，不作为准入门槛；`05b` 把“≥2 个不同 `source_file`”变成硬门槛。
- 给“内容偏薄”提供了可审计的增量：6 条候选、9 个 `[待确认]` 标记、21 条可追溯引用。
- 没有解决 `02` 偏薄、`01` 身份零命中、3 条主线冲突；这些必须本人确认，不能靠 L2 自动补。

## 6. 下一步

1. 本人从 `docs/confirmation-pack.md` 回答 A/B/C/D 四组。
2. 把确认项写回 `01`~`04`，只保留 1 条当前主线。
3. 重装补强后的薄 `AGENTS.md`（1,701 bytes，含“动前先思/不盲猜”）。
4. `review --confirm`，再由独立 Agent 做三问盲测。
5. 盲测通过后，才允许把 `[待确认]` 转正；否则仍停在 `pending_review`。