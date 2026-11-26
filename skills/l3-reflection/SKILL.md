---
name: l3-reflection
description: 离线 L3 反思引导规范（Raw Facts → Observations → Mental Models）。仅在 L1/L2 验收达标后由接手 Agent 按需调用，所有候选必须通过 scripts/12_l3_reflection_gate.py 四道硬门禁并经本人签字，严禁自动写入 6 份正式档案。
---

# L3 反思引导 Skill（轻量化离线归纳 · 严禁越权落盘）

## 一、启用前置条件（缺一不可）

1. L1（`6-File Onboarding Kit`）与 L2（差集挖掘 + 图谱冲突去噪）已完成验收；
2. 仅读取只读冷库（`unified_index.db`）中的 `user` 角色原话与干净 L1/L2 产物；
3. **本 Skill 只产出待审 JSONL 候选，绝不直接修改任何正式 6 份档案。**

## 二、反思输入与输出契约

输入：
- 冷库 `records`（仅 `role == 'user'`）
- 已验收的 6 份档案 + `layer2/l2_candidates.md` + 图谱冲突清单（`06_graph_index.py --action conflicts`）

输出（JSONL，每行 1 条 `Observation` 候选）：
```json
{
  "observation_id": "OBS-001",
  "statement": "跨多轮真实经历归纳出的稳定规律（不能复述单句原话）",
  "evidence": [
    {"rec_id": "REC-0001", "quote": "冷库中逐字存在的原文片段 1"},
    {"rec_id": "REC-0018", "quote": "另一日期且另一会话中逐字存在的原文片段 2"}
  ],
  "counterexamples": [
    {"rec_id": "REC-0025", "quote": "例外或反转原话（若确实无反例则显式写 []）"}
  ],
  "evolution": "写清首次出现、复现与例外边界的时间演变，而不是静态定论"
}
```

## 三、四道 Python 程序化硬门禁（`scripts/12_l3_reflection_gate.py`）

产出候选后，必须运行：
```powershell
python -X utf8 scripts/12_l3_reflection_gate.py --db work/unified_index.db --observations work/l3_observations.jsonl --json
```

四道机械判定（不设主观百分比打分）：
1. **`G1_MULTI_EVIDENCE`**：至少引用 `≥2` 条不同日期且不同会话（`source_file`）的真实 `user` 记录，且每条 `rec_id` 与 `quote` 均在冷库原文精确命中；
2. **`G2_L2_PARAPHRASE`**：与单条引用原话或 L2 候选字面重合过高（仅换词复述单句）即直接淘汰；
3. **`G3_COUNTEREXAMPLE_AND_EVOLUTION`**：必须显式保留 `counterexamples` 槽位（每条反例同样验真）与非空 `evolution` 演变历史；
4. **`G4_HUMAN_SIGNOFF_REQUIRED`**：未经本人明确签字（`status=signed`、`signed_by`、`signed_at`、`confirm=True`），机械阻断任何写入 `02-核心判断准则.md` 或 `04-正反例避坑账.md` 的动作；`AGENTS.md` 永久只读。
