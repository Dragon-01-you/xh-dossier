# Docker 跑 Windows 的白话原理（dockur/windows）

> 先给结论：**Docker 本身不虚拟一台 Windows。** `dockur/windows` 是在 Linux 容器里塞进一台完整的 Windows 虚拟机：Docker 只是外壳，QEMU/KVM 才是“真机”的那一层。
>
> 官方依据：<https://github.com/dockur/windows>（2026-11-25 读取 README）

## 1. 三层拆开看

```text
你的 Windows 11
└─ Docker Desktop（Linux 容器引擎）
   └─ dockur/windows 容器
      └─ QEMU + KVM
         └─ 完整 Windows 虚拟机（有自己的 BIOS、磁盘、网卡、桌面）
```

- **Docker 层**：负责拉镜像、起容器、挂目录、开端口。它不提供 Windows 内核。
- **QEMU 层**：模拟主板、CPU、磁盘、网卡、USB、显示。
- **KVM 层**：把 CPU 虚拟化指令直通给虚拟机，所以“接近原生速度”；没有 KVM 就只能纯软件模拟，慢到不适合日常。
- **Windows 层**：是一台真的 Windows，不是 Wine，也不是“兼容层”。它有自己的激活、登录、桌面、浏览器。

所以“Docker 怎么模拟出一台真机”这句话要改一下：**Docker 不模拟真机；它把一台真机的零件（QEMU/KVM + Windows 镜像）装进容器里，再给你一个网页/RDP 窗口。**

## 2. 它到底做了什么

1. 首次启动，容器下载 Windows ISO（默认 Windows 11 Pro，约 7.9GB；`11l` LTSC 约 4.7GB）。
2. 自动分区、安装、创建默认用户 `Docker`，密码 `admin`。
3. 把 VM 磁盘放在你挂载的 `/storage` 目录里（默认 64GB，可改 `DISK_SIZE`）。
4. 开两个口：`8006` 网页桌面（安装时看画面）、`3389` RDP（日常更流畅）。
5. 挂一个 `/shared` 目录，宿主机和 VM 交换文件。
6. 关机再开，磁盘还在；删掉 `storage` 目录，就是一台全新机器。

这就是它解决“别人也能跑”的核心：**环境是可复制、可重置、可干净复跑的**。不是把作者的登录态复制给别人，而是给别人一台干净的机器，让他自己登录。

## 3. 哪些能、哪些不能

| 能做 | 不能做 / 边界 |
|---|---|
| 在 Windows 11 上起一台隔离 Windows VM | Windows 10、macOS 的 Docker Desktop 不提供 KVM，官方明确不支持 |
| 自动安装 Windows、自动配 CPU/内存/磁盘 | 需要宿主机有 KVM；本机 Docker Desktop 要开嵌套虚拟化 |
| 网页看安装、RDP 日常用 | 网页桌面不适合长期办公，剪贴板/流畅度不如 RDP |
| 共享目录交换导出文件 | 不能把“别人的登录态”打包进去；每个用户自己登录 |
| 删 storage 重置干净房 | 不能替代“本人签字/本人访谈/本人确认扩展” |

## 4. 为什么它适合“干净房”，不适合当普通用户唯一入口

- 普通用户先要装 Docker Desktop，这本身就是一个比装 Python 更重的前置。
- 一台 15GB 内存的笔记本，只能舒服地跑 1 个 6–8GB VM；2 个 4GB 很紧，3 个不现实。
- 它的价值是“验收/演示/复现”，不是“多人云桌面”。

**推荐组合**：

1. **普通用户**：本机直接跑 Agent + 本机 Edge，按 `docs/agent-env-bootstrap.md` 装；不要求 Docker。
2. **干净复跑/验收**：本机 Docker Desktop + `dockur/windows`，一台干净 Windows VM；共享目录只交换 `raw/` 和产物。
3. **开发者**：Linux + Docker + KVM 跑同样的 compose，CI 里做代码层，不做桌面层。

## 5. 本机最小 compose（Windows 11）

```yaml
services:
  windows:
    image: dockurr/windows
    container_name: xh-windows-clean
    environment:
      VERSION: "11l"          # 4.7GB LTSC；想用 Pro 改 "11"
      DISK_SIZE: "64G"
      RAM_SIZE: "8G"
      CPU_CORES: "6"
    devices:
      - /dev/kvm
      - /dev/net/tun
    cap_add:
      - NET_ADMIN
    ports:
      - "8006:8006"
      - "3389:3389/tcp"
      - "3389:3389/udp"
    volumes:
      - "D:/xh-vm/windows:/storage"   # 必须放 D 盘，C 盘只剩 6GB
      - "D:/xh-vm/shared:/shared"
    restart: always
    stop_grace_period: 2m
```

启动后浏览器开 `http://127.0.0.1:8006` 看安装；装完用 `mstsc` 连 `127.0.0.1:3389`，账号 `Docker` / `admin`（首次登录后改密码）。

> 本机已验证的部分：Docker Desktop 29.8.0（Linux engine）能启动，容器内能看到 `/dev/kvm` 与 `/dev/net/tun`；**尚未完成完整 Windows ISO 下载与首次启动**，所以不能说“Windows VM 已跑起来”。这一步需要本机在线并空出 D 盘 4.7GB+64GB。

## 6. 一句话记忆

**Docker 是集装箱，QEMU/KVM 是发动机，Windows 是货物。** 集装箱让货物可搬运、可复制；发动机才让 Windows 真的跑起来；登录、扩展、签字仍然是人做的事。
