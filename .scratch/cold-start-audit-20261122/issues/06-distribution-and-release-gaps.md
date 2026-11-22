# 06 · 分发与发布面缺口：无 doctor、无 release、CI 单平台且不跑 strict

Status: needs-triage
Type: task
Priority: P2
Step: S1 / S9 / S10

## 现象

| 检查项 | 实测 |
|---|---|
| `scripts/00_doctor.py` | 不存在 |
| `pyproject.toml` / 入口点 | 不存在；`pip install .` → “Neither 'setup.py' nor 'pyproject.toml' found” |
| git tag / release | 空 |
| `VERSION` / `CHANGELOG.md` / `known-limits.md` / `SHA256SUMS` | 全部缺失 |
| CI 矩阵 | 仅 `ubuntu-latest` + Python 3.12 |
| CI 验收路径 | 只跑 `--target templates`，**不跑 `--strict`** |
| `.scratch` 是否忽略 | 未忽略（但 AGENTS.md 要求 issue 写这里） |

另外：

- 无浏览器时 `00_export_wizard.py` 仍打印 `OPENED_OK`（`webbrowser.open` 返回 False）；
- `--download-release` 在 GitHub API 403 时输出原始 traceback；
- wizard 不校验下载包 SHA256；
- Greasyfork 不可达时无 fallback（官方源码在 `AfterThink/AfterChat-Script`，AGPL-3.0）。

## 期望

- `00_doctor.py`：Python ≥3.11、SQLite ≥3.34、FTS5/trigram 真建表、目录可写、依赖齐全；输出 `DOCTOR_OK`；
- CI：Windows + Ubuntu × 3.11/3.12，并跑 `--strict` 与敌意语料；
- 发布：tag + zip + SHA256SUMS + VERSION + CHANGELOG + known-limits；
- wizard：`OPENED_OK` 仅在 `webbrowser.open` 返回 True 时打印；加 GitHub fallback 与校验和；说明 AfterChat 不随包分发（AGPL）。

## 证据

- `/tmp/xh-run/evidence/s1-failpaths.txt`
- `/tmp/xh-run/evidence/final-verify.txt`
- `.github/workflows/ci.yml`

## 最小修复

按 S1→S9→S10 顺序补；`pyproject.toml` 需先把数字开头的模块重命名（`console_scripts` 不接受 `01_clean_and_index`）。
