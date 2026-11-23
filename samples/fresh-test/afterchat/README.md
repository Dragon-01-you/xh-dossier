# AfterChat 真实导出样本（issue #61 归档）

## 用途

本目录存放从本机真实运行导出中挑选、并经过脱敏的 AfterChat / DeepSeek 对话导出片段，
用于对照 issue #61「真实 AfterChat 导出格式缺独立测试 fixture」所描述的解析风险：

- 回合头识别：`### 🧑‍💻 User` / `### 🤖 Assistant` 角色不错分；
- 元数据识别：`## Metadata` 块里的 `**Time:**` 被读取，`created_at` 不应全部为 unknown；
- 块级内容识别：代码块、表格、ASCII 图、引用附件的回合不被误判为用户记录；
- 思考块：解析器不应把助手内部过程块误判成 user 记录（本批真实导出中未出现 `<think>` 标签，
  该关注点留待后续真实样例补充）。

## 样本清单

| 编号 | 文件 | 覆盖特征 | 来源形态 |
|---|---|---|---|
| AC-01 | `sample-ac-01-single-turn.md` | emoji 回合头、Metadata Time 块、单轮问答 | 单轮真实导出，节选 |
| AC-02 | `sample-ac-02-multiturn-longtext.md` | 多轮长文、长段落、bash 代码块、配置表格、ASCII 流程节选 | 多轮真实导出，节选 |
| AC-03 | `sample-ac-03-image-attachment-reference.md` | 用户引用上传图片附件、HTML 代码块围栏 | 含图片引用的真实导出，节选 |

## 来源说明

- 原始材料来自本机一次真实运行留下的对话导出归档（对话导出目录，约 100 份 DeepSeek 导出），
  以及同次运行的访谈记录文件。本仓库只保留相对描述，**不记录用户名、本机账号或会话链接**。
- 原文未整份复制入库：每份样本只保留结构片段与必要上下文，长段正文以省略标记注明，控制归档体量。

## 脱敏规则

1. 会话链接（聊天平台会话 URL）替换为占位符 `<chat-url>`；
2. 真实 GitHub 账号 / 仓库名替换为 `<github-owner>/<github-repo>`；
3. 个人称呼、别名替换为 `<称呼>`；演示用代号 / 标题替换为 `<demo-title>`；
4. 公开品牌、机构名等词典类条目按样本需要节选或泛化为 `<品牌名 X>`，不作为个人信息处理；
5. **保留**原有结构、emoji、时间格式（`YYYY-MM-DD HH:mm:ss`）、标点与句法特征；
6. 逐条替换对照见 `../../REDACTION-MAP.md`。

## 不进 pytest / CI 声明

- 本目录全部为 **Markdown 归档样本**，不是 `test_*.py`，不在 `tests/` 目录下，
  不会被默认 `pytest` 收集，也未被任何测试脚本引用。
- 本 PR **不接入正式 pytest、不进 CI**；`.github/workflows/` 未做任何改动。
- 未来若要把真实格式固化成解析 fixture，应另走代码票评估接入方式，不在本归档 PR 范围内。
