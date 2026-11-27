# Issue tracker: GitHub Issues

这个仓库的 spec 和工单都放在 GitHub issue 里，仓库是 `Dragon-01-you/xh-dossier`。仓库内的 `.scratch/` 本地 markdown 流程已废弃。

## 约定

- **Spec**：一个 issue，标题以 `[Spec]` 开头，打 `ready-for-agent`。
- **工单**：一个 issue 一张工单，垂直切片，独立可验收。正文含 `## Parent`（指向 spec issue）与 `## Blocked by`（列出阻塞它的 issue 编号）。
- **阻塞边**：用正文的 `## Blocked by` 文本表达；列出的 issue 全部关闭，这张工单才算 unblocked。
- **状态**：只用五个标签，见 `triage-labels.md`：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。
- **讨论**：在该 issue 下追加评论，不另开新 issue。
- **关闭**：只在验收标准全部勾上后关闭。

## 常用操作

```powershell
# 创建（用 --body-file 避免中文编码问题）
gh issue create --repo Dragon-01-you/xh-dossier --title "<title>" --body-file <path> --label ready-for-agent

# 读取全文
gh issue view <N> --repo Dragon-01-you/xh-dossier --json title,body,labels,state

# 列出可开工的 frontier
gh issue list --repo Dragon-01-you/xh-dossier --state open --label ready-for-agent --limit 100

# 追加评论
gh issue comment <N> --repo Dragon-01-you/xh-dossier --body-file <path>

# 关闭
gh issue close <N> --repo Dragon-01-you/xh-dossier
```

## 给 Agent 的提示

- 开工前先读 spec issue，再读自己那张工单和它的 `Blocked by`。
- 在 `reflow-v1` 分支上开自己的子分支，不要直接推 `main`。
- 交付时必须附“改前 / 改后”两行台账，见 spec 的“监控”一节。
