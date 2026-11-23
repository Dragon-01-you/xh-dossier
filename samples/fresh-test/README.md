# fresh-test 真实脱敏样本集（issues #61 / #63 归档）

## 用途

本目录为 issue #61、#63 归档一批**真实、已脱敏**的参考样本，用于人工核对与后续规则固化：

- `afterchat/` —— 真实 AfterChat / DeepSeek 对话导出格式样本（#61）；
- `semantic-cases/` —— 抽象偏好句、长句、方言口语、中英 / 代码混句、打断句等语义案例（#63）。

这些样本是**归档参考材料**，不是产品代码，也不是测试固件。

## 目录结构

```
samples/fresh-test/
├── README.md                      # 本文件：总览、来源、脱敏总规则、不进 CI 声明
├── REDACTION-MAP.md               # 脱敏前形态（抽象描述）→ 脱敏后片段逐条对照（核对用）
├── afterchat/
│   ├── README.md
│   ├── sample-ac-01-single-turn.md
│   ├── sample-ac-02-multiturn-longtext.md
│   └── sample-ac-03-image-attachment-reference.md
└── semantic-cases/
    ├── README.md
    ├── cases-abstract-preference.md
    ├── cases-long-utterance.md
    ├── cases-colloquial-dialect.md
    ├── cases-mixed-language-code.md
    ├── cases-interruption.md
    └── cases-positive-negative.md
```

## 来源说明

- 原始材料来自本机一次真实运行留下的归档：
  - 对话导出目录（约 100 份 DeepSeek 导出，只读挑选）；
  - 同次运行的访谈记录文件（6 轮用户原话逐条记录）。
- 本仓库只保留相对描述，**不记录用户名、本机账号、群名或会话链接**；
  原始整份材料未复制入库，每类仅节选 2–5 条，长段以省略标记注明。

## 脱敏总规则

| 类别 | 处理方式 | 占位符 |
|---|---|---|
| 会话 / 页面 URL | 整体替换 | `<chat-url>` |
| GitHub 账号 / 仓库名 | 整体替换 | `<github-owner>/<github-repo>` |
| 个人称呼、别名、旧昵称 | 整体替换 | `<称呼>` |
| 演示代号 / 页面标题 | 整体替换 | `<demo-title>` |
| 公开品牌 / 机构词典条目 | 按样本需要节选或泛化 | `<品牌名 X>` |
| 公开产品 / 平台名（Notion、IMA、闲鱼等） | 作为普通名词保留，不作个人信息处理 | — |
| 时间格式、emoji、标点、句法结构 | **原样保留** | — |

逐条“脱敏前形态（抽象描述）→ 脱敏后片段”对照见 `REDACTION-MAP.md`。

## 不进 pytest / CI 声明

- 本目录全部为 Markdown 归档样本与案例，**不是 `test_*.py`**，不在 `tests/` 目录下，
  不会被默认 `pytest` 收集，也未被任何测试脚本或流水线引用。
- 本 PR **不接入正式 pytest、不进 CI**；`.github/workflows/` 未做任何改动，main 分支未合并。
- 未来若要把真实格式固化为解析 fixture 或正式规则样本，应另走对应代码 / 方法票评估。

## 边界

- 样本只反映本次本机运行的真实语料，不代表产品承诺或通用口径；
- 语义案例的人工打分尚未完成（均为 `[待打分]`），打分前不得作为规则依据；
- 语音误写、含义待确认的专名已整条排除，未纳入案例集。
