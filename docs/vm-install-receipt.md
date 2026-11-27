# Windows VM 干净房安装回执（2026-11-25）

> 目的：证明“不是只有作者机能跑”。在一台由 `dockur/windows` 新建的 Windows 11 Enterprise LTSC 评估版 VM 里，从共享盘安装 XH-Dossier，并跑通安装、体检、样例。

## 1. 机器

| 项 | 值 |
|---|---|
| 宿主 | Windows 11，Docker Desktop 29.8.0，Linux engine |
| 虚拟化 | WSL2 + QEMU/KVM，容器内 `/dev/kvm`、`/dev/net/tun` 可见 |
| 客户机 | Windows 11 Enterprise LTSC（Evaluation），Build 26100，用户 `Docker` |
| VM 配置 | 6GB RAM / 8 vCPU / 64GB 磁盘 |
| 共享盘 | `D:\XH-Windows\shared` → VM 内 `Z:`（`\\host.lan\Data`，302.40GB used / 32.68GB free） |
| 网页桌面 | `http://localhost:8006`（noVNC，HTTP 200） |
| RDP | `localhost:3389`（`Docker` / `admin`） |

## 2. 安装包

- `Z:\xh-dossier-20261125.zip`（0.33MB，109 files）
- `Z:\python-3.12.10-embed-amd64.zip`（10.62MB，已验证 `Python 3.12.10`）
- `Z:\XH-Install.ps1`（2,865 bytes）

## 3. 安装命令与回执

在 VM 的 Administrator PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File Z:\XH-Install.ps1
```

`xh-install-log.txt` 的关键标记：

```text
INSTALL_OK
DOCTOR_OK
DEMO_OK
INIT_OK
VM_INSTALL_OK
```

关键路径：

```text
Python: C:\Users\Docker\AppData\Local\XH-Dossier\python\python.exe  (3.12.10)
Repo:   C:\XH\XH-Dossier
Work:   C:\XH\XH-Dossier\work
Kit:    C:\XH\XH-Dossier\work\kit
Receipts:
  work/xh-build.json
  work/xh-demo.json
  work/xh-doctor.json
  work/xh-init.json
```

注意：`xh.py init` 写入的是空白模板，`work/kit` 里的占位符未填；这是预期，不是安装失败。安装脚本末尾明确写了：

> 现在 `work/kit` 是空白模板，里面的 `<...>` 还没填。这时直接跑 `validate --strict` 会报占位符，这不是安装失败。下一步：把聊天记录放进 `work/raw` 后跑 `build`；或先做六阶段访谈，再校验。

## 4. 浏览器层检测

在 VM 内执行：

```text
Z:\run-env-check.cmd
```

输出：

```text
=== XH-Dossier onboarding environment check ===
[OK     ] os: Windows 11
[OK     ] browser: C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
[MISSING] userscript_manager: 未检测到 Tampermonkey / ScriptCat；请到 edge://extensions 确认
[MISSING] afterchat: 未检测到 AfterChat；若已安装请打开管理器面板确认状态为「启用」
[MISSING] login: 未检测到豆包/DeepSeek/ChatGPT 等登录 Cookie；请在本机日常浏览器登录
[OK     ] download_dir: C:\Users\Docker\Downloads（可写）
[INFO   ] browser_control: 未安装 sctl；只有需要 Agent 控制浏览器时才需要

ENV_BLOCKED: userscript_manager, afterchat, login
```

## 5. 结论

- **环境层安装已闭环**：干净 VM 里能装 Python、能解压 repo、能跑 `doctor` / `demo` / `init`，退出码都是 0。
- **浏览器层停在人类门**：Tampermonkey、AfterChat、豆包登录必须本人做；Agent 不静默装扩展、不代登录。
- **不能宣称“导出已跑通”**：`ENV_BLOCKED` 是明确的停止信号；装好扩展并登录后，再跑同一脚本复测。

## 6. 复测命令

```powershell
# VM 内
Z:\run-env-check.cmd
# 期望：ENV_BLOCKED 消失，出现 ENV_OK / 可进入 S4 导出闸门
```

宿主查看回执：

```powershell
Get-Content D:\XH-Windows\shared\env-check.log
Get-Content D:\XH-Windows\shared\xh-install-log.txt -Tail 40
```