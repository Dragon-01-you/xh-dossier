# Agent 环境配置协议（v0.1）

> 目标：把“我这台能跑”变成“换一台也能跑”。用户只做三件人类动作：**装扩展确认、登录、签字**；其余由 Agent 检查、安装、重试、验收。
>
> 适用：Windows 11 + Edge 的普通用户；也适用于 Linux 干净房（没有浏览器导出能力时只跑代码层）。
> 关联：`docs/00-install-one-click.md`（浏览器直达链接）、`docs/02-multi-platform-export.md`（导出范围）、`docs/testing-environment.md`（测试环境）。

## 0. 先分清四层，不要混在一句话里

| 层 | 谁来做 | 通过标准 | 失败时 |
|---|---|---|---|
| L0 代码层 | Agent | `python scripts/xh.py doctor` 返回 `DOCTOR_OK`；`pytest` 全绿 | 停在代码层，不碰浏览器 |
| L1 依赖层 | Agent | Python ≥3.11、repo 可读、模板齐全、`work/` 可写 | 下载便携 Python / 重解压 repo；不静默改系统 |
| L2 浏览器层 | 人 + Agent 检查 | Edge / 脚本管理器 / AfterChat / 登录 / 下载目录五项齐全 | 输出 `ENV_BLOCKED` + 直达链接，不继续导出 |
| L3 产品层 | 人 | 真实访谈、真实导出、本人签字、盲测 | Agent 只记录回执，不代签 |

**边界**：浏览器的扩展安装、账号登录、系统“另存为”、本人签字，Agent 不能代做，也不应该绕过。Agent 能做的是打开官方页面、核对 ID、检测状态、等用户点完再复测。

## 1. Agent 启动提示词（可直接复制）

```text
你是 XH-Dossier 的环境配置 Agent。目标不是“解释怎么装”，而是把当前机器配到能真实跑通，
并输出一份带命令、退出码和回执的证据。

硬规则：
1. 先检查，后安装。每一步先跑检查命令，拿到真实输出再决定下一步。
2. 只读检查可并行：Python / repo / 磁盘 / 浏览器 / 扩展 / 登录 / 下载目录。
   安装、写文件、登录、导出必须串行，避免互相打架。
3. 不静默安装浏览器扩展；不代登录；不代点系统“另存为”；不代签字。
4. 缺件就停，输出 ENV_BLOCKED 和下一 action；不要用自建后台或 DOM 兜底绕过。
5. 任何“已通过”必须附命令、退出码、回执路径；没跑过就写“未跑”。

顺序：
S0 机器体检：OS、Python、架构、内存、磁盘、网络、是否已有 Docker/KVM。
S1 代码层：克隆/解压 repo → `python scripts/xh.py doctor` → `pytest -q`。
S2 样例层：`python scripts/xh.py init` → `python scripts/xh.py demo` → 看到 `DEMO_OK`。
S3 浏览器层：`python scripts/00_env_check.py --browser edge --dry-run`；
   按 docs/00-install-one-click.md 给直达链接，等用户装完/登录完再复测。
S4 导出层：用户真实点一次导出；`python scripts/10_export_gate.py --raw work/raw/afterchat --download-dir <dir>`。
S5 干净复跑：新目录再跑一次 S1-S3，确认不是“只有旧目录能跑”。
S6 输出回执：environment-receipt.json + 失败项 + 下一 action。
```

## 2. 分阶段命令（Windows PowerShell 7）

```powershell
# S0 机器体检（只读）
py -3.12 -X utf8 scripts/xh.py doctor

# S1 代码层
git clone https://github.com/Dragon-01-you/xh-dossier.git
cd xh-dossier
py -3.12 -m pytest -q

# S2 样例层
py -3.12 -X utf8 scripts/xh.py init
py -3.12 -X utf8 scripts/xh.py demo

# S3 浏览器层
py -3.12 -X utf8 scripts/00_env_check.py --browser edge --dry-run
# 装完扩展、登录后复测
py -3.12 -X utf8 scripts/00_env_check.py --browser edge --confirm-login

# S4 导出闸门（示例目录，按实际改）
py -3.12 -X utf8 scripts/10_export_gate.py --raw work/raw/afterchat --download-dir "D:\XH-Downloads"

# S5 干净复跑
cd ..
git clone https://github.com/Dragon-01-you/xh-dossier.git xh-clean
cd xh-clean
py -3.12 -X utf8 scripts/xh.py demo
```

## 3. 失败码与下一步

| 输出 | 含义 | Agent 下一步 |
|---|---|---|
| `DOCTOR_OK` | Python/脚本/模板/work 基本可用 | 进入 S2 |
| `DOCTOR_FAIL` | 缺 Python 或模板/脚本不全 | 安装 Python 3.12 或重新解压 repo；不要继续 |
| `ENV_BLOCKED` | 浏览器五项有缺件 | 给对应直达链接，等用户确认后复测 |
| `EXPORT_BUTTON_MISSING` | 页面没有 AfterChat 按钮 | 查管理器是否启用、MV3 用户脚本开关、强刷 |
| `DOWNLOAD_INTERRUPTED` | `.crdownload` 未收尾 | 查 `Ctrl+J`；用 `11_finalize_download.py` 恢复副本，不宣称浏览器已修好 |
| `VERIFY_BLOCKED_REVIEW` | 六份档案未本人复核 | 停在签字门；不要跑盲测或发布 |

## 4. 一台电脑怎么“模拟另一台干净电脑”

不需要第二台物理机，推荐两种：

1. **干净目录复跑**（最低成本）：新 clone 到 `D:\xh-clean-*`，新 `work/`，跑 `doctor/demo`。这能抓“只对旧目录生效”的路径/缓存 bug。
2. **Windows VM 干净房**（最接近真实用户）：在本机 Docker Desktop 里跑 `dockur/windows`。Windows 11 + 嵌套虚拟化；VM 内装 Python、Edge、脚本管理器、AfterChat；共享目录只交换导出文件。详见 `docs/docker-windows-plain.md`。

**不要把它说成“多人服务器”**：本机 15GB 内存只适合 1 个 6–8GB Windows VM；2 个 4GB 很紧，3 个不现实。它的用途是“干净复跑 / 演示 / 验收”，不是给很多用户同时开桌面。

## 5. 验收回执（Agent 必须落盘）

```json
{
  "host": {"os": "...", "python": "...", "ram_gb": 0, "disk_free_gb": 0},
  "layers": {
    "code": {"doctor": "DOCTOR_OK", "pytest": "280 passed", "exit": 0},
    "demo": {"build": "BUILD_OK", "validate": "VALIDATE_OK", "exit": 0},
    "browser": {"env_check": "ENV_BLOCKED|ENV_OK", "missing": []},
    "export": {"gate": "PASS|EXPORT_BUTTON_MISSING|DOWNLOAD_INTERRUPTED"}
  },
  "human_actions": ["install_extension", "login", "sign"],
  "blocked_by": "...",
  "next_action": "..."
}
```

> 一句话：Agent 负责“装、跑、验”，人负责“点三下”。任何一层没回执，就不能说整条环境跑通。
