# 测试环境说明 · 家庭版无 Sandbox 的取证结论与不改系统的替代方法（Issue #101 / Epic #75）

> 性质：**方法文档（method）**。本票不改产品代码，也不在 `scripts/` 里加拦截；
> 只记录"这台家庭版机器为什么用不了 Windows Sandbox"，以及在**不改系统、不申请提权**前提下，
> 怎么把管线测干净。

---

## 一、取证结论：家庭版无法使用 Windows Sandbox

### 1.1 实测环境（Gate0 g1 取证记录，ISSUE-001 / ISSUE-002）

| 取证项 | 实测值 | 含义 |
|---|---|---|
| ProductName | `Windows 10 Home China` | 家庭中文版 SKU |
| EditionID | `CoreCountrySpecific` | 核心国家 specific 版，**不含 Windows Sandbox 可选功能** |
| DisplayVersion | `25H2` | 功能版本 |
| CurrentBuild / UBR | `26200` / `9974` | 系统内部版本 |
| `WindowsSandbox.exe` | `False`（未找到） | 系统里没有沙箱可执行文件 |
| `dism.exe` | `True`（存在） | 命令在，但功能安装走不通 |
| DISM 输出 | `Error: 740` / `Elevated permissions are required to run DISM...` | 需要提权才能改功能，当前进程不满足 |
| 权限组 | `BUILTIN\Administrators … Group used for deny only` | 管理员组只用于拒绝，当前不是提权令牌 |
| 完整性级别 | `Medium Mandatory Level` | 中等完整性，非提升权限进程 |

**结论（三条，不引申）：**

1. Windows Sandbox 是专业版/企业版等 SKU 的可选功能；家庭中文版（CoreCountrySpecific）本身不带该功能，`WindowsSandbox.exe` 不存在。
2. 当前账户运行在中等完整性、管理员组 deny-only 的非提权状态；DISM 报 740，无法在线安装或启用系统可选功能。
3. 本票**不要求**关闭 UAC、不要求强行提权、不要求改注册表或系统组件；沙箱类方案在这台家庭机器上标记为"不可用"，改用下面的替代方法。

### 1.2 可复跑的取证命令（本人在场时复核）

```bat
:: 系统版本（ProductName / EditionID / Build）
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v ProductName
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v EditionID

:: 沙箱可执行文件是否存在（where 返回空即不存在）
where WindowsSandbox.exe

:: 当前完整性级别与管理员组归属
whoami /groups

:: 可选功能列表（必须提权的管理员终端才能跑；普通终端会复现 740）
dism /online /get-features /format:table
```

> 740 只代表"需要提权"，不代表"功能已被禁用"；在家庭版上即使提权，Sandbox 功能也未必在可选列表里——这一点未在专业版机器上复核，标 UNVERIFIED。

---

## 二、不改系统的替代测试方法

目标：把管线（清洗去重 / 四路匹配 / 档案校验 / 样例入库）在一个**可丢弃、可复现**的环境里测干净，所有写入只落在仓库工作目录或独立临时目录，不碰系统目录、注册表和全局环境。

### 方法 A：净化 profile（隔离目录跑管线）

适合：想在本机测，但不希望测试过程污染真实用户配置。

1. 新建一个独立目录当隔离根，例如仓库同级的 `clean-profile/`；
2. 为测试进程单独设置这些变量，全部指向隔离根下的子目录：
   - `USERPROFILE`、`APPDATA`、`LOCALAPPDATA`、`TEMP`、`TMP`；
   - `PATH` 只保留 Python 解释器与仓库运行必需条目；
3. 剥离代理、自定义 Shell 偏好、全局 npm/pip 配置等会影响结果的环境变量，需要联网时再按白名单逐个恢复；
4. 在该环境里拉同一基线、跑 `00_doctor.py`、全量 `pytest` 和 `examples/sample_raw` 样例入库；
5. 测完删除隔离根目录即可。

**边界（不要高估它）：** 净化 profile 模拟的是"干净的用户配置环境"，**不是沙箱隔离**——进程仍在同一操作系统内，仍可读本机其他文件；它只能证明管线在干净配置下行为正确，不能代替隔离级别的安全测试。

### 方法 B：云主机 / 一次性干净环境

适合：需要一个与本机配置无关、可整体销毁的环境。

1. 开一台可丢弃的云主机（Linux 或 Windows），拉同一基线 commit；
2. 在云主机上跑 doctor、全量 pytest、样例 ingest + match、模板校验、打包往返；
3. 测完销毁实例，本机不残留测试产物。

**边界：** 本轮未做 Linux 全量覆盖性验证；云主机的网络、代理、字体、SQLite 编译选项与家庭机器不同；需要浏览器登录态的网页导出测试，云主机里同样做不了，仍须真人在已登录浏览器在场操作。

### 方法 C：临时目录内只读冒烟

适合：快速判断当前仓库能不能跑通主链路，不准备长期测试。

- 用 `examples/sample_raw` 样例入库，跑关键词回查；
- 运行 `scripts/99_smoke.py` 冒烟脚本；
- 所有产物写进仓库 `work/` 目录或系统临时目录；doctor 的写探针跑完自删（见 `00_doctor.py` 的 `check_workdir`）。

---

## 三、与现有 doctor 的关系

`scripts/00_doctor.py` 目前只检查四件事：

- Python ≥ 3.11；
- SQLite FTS5 + trigram 真建表 / 插入 / 查询；
- 仓库根目录存在、工作目录可写；
- 必需脚本与 6 份模板齐全。

它**不**检测 Windows 版本、不检测 Sandbox 是否可用，也**不**按家庭版做拦截。这是刻意保留的边界：家庭版用户仍能跑后端管线，缺的只是沙箱这一种隔离方式。本票不在 doctor 里新增家庭版门禁，避免把能正常使用的用户挡在门外。

---

## 四、边界与未覆盖事项

- 未提权状态下取得的 DISM 740 结果；家庭版升级到专业版后 Sandbox 是否可启用，未在真实专业版机器复核（UNVERIFIED）。
- 未做 Linux 全量行为覆盖；跨平台编码、解压乱码等平台相关项以各自环境实测为准。
- 浏览器登录态导出、扩展开关、批量确认门属于真人在场操作，不在后端自动化测试范围（见 [02-multi-platform-export.md](02-multi-platform-export.md)）。
- 本方法文档不替代正式的隔离/安全评审；若未来需要隔离级测试，应在具备 Sandbox 或容器的环境中另立任务。
