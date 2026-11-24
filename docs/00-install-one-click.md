# 先点这里：XH-Dossier 浏览器前置安装

> 这一页只做一件事：让你用最短路径把“能导出聊天”和“能让 Agent 控制浏览器”两件事装齐。
>
> **缺一件就停。** 不要跳过安装继续跑，也不要因为没装扩展就临时做一个自己的后台。浏览器安全不允许静默安装扩展；产品能做的是检查和引导，安装确认必须由你本人在浏览器里点。

## 1. 先选一条路径

| 你要做的事 | 需要装什么 | 不需要装什么 |
|---|---|---|
| 只导出自己的聊天记录，交给 XH-Dossier 建档案 | 一个脚本管理器 + AfterChat | 不需要 sctl，不需要 Playwright |
| 让 Agent 替你点页面、切标签、截图、读控制台 | 上面两样 + sctl Browser + sctl CLI | AfterChat 不能代替浏览器控制 |
| 你是开发者，已有 Playwright / Chrome DevTools | 一个已登录浏览器 + CDP 连接 | 普通用户不需要走这条 |

> 脚本管理器只选一个：Tampermonkey 或 ScriptCat。已经装了哪个就用哪个，不要为了“齐全”再装第二个，两个管理器同时跑同一脚本容易互相打架。

## 2. 直达链接（点开就能装）

### 路径 A：Tampermonkey + AfterChat（普通用户最短路径）

1. **装管理器（Edge）**：  
   https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd
2. **装导出脚本 AfterChat**：  
   https://greasyfork.org/en/scripts/589622-afterchat-llm-chat-exporter  
   打开后点「Install this script / 安装此脚本」，在确认页再点一次「安装」。
3. **不想走 GreasyFork 时的直装地址**（仍然要在管理器里确认安装）：  
   https://raw.githubusercontent.com/AfterThink/AfterChat-Script/main/afterchat.user.js
4. **源码/版本核对**：  
   https://github.com/AfterThink/AfterChat-Script

### 路径 B：ScriptCat + AfterChat（想同时用 sctl 控制浏览器）

1. **装管理器（Edge）**：  
   https://microsoftedge.microsoft.com/addons/detail/%E8%84%9A%E6%9C%AC%E7%8C%AB/liilgpjgabokdklappibcjfablkpcekh
2. **装 AfterChat**：同上，GreasyFork #589622 或 raw `.user.js`。
3. **装浏览器控制扩展 sctl Browser（Edge）**：  
   https://microsoftedge.microsoft.com/addons/detail/sctl-browser/nbmnkdfbjdhbdjjffgkocfdkemockepa
4. **装 sctl CLI**（需要 Node/npm 或官方 release）：  
   https://github.com/scriptscat/sctl
5. **配对与命令文档**：  
   https://docs.scriptcat.org/en/docs/use/sctl-browser/

> sctl Browser 是高权限扩展：配对后，任何能跑 sctl 的程序都可以读改标签页、Cookie、历史、页面内容和网络请求。只给你信任的 Agent 用；建议单独开一个浏览器 profile 做自动化。

## 3. 装完必须过的 5 个检查

| # | 检查 | 通过标准 | 不通过怎么办 |
|---|---|---|---|
| 1 | 管理器在不在 | `edge://extensions` 能看到 Tampermonkey 或 ScriptCat，且是启用状态 | 回第 2 节点对应链接安装 |
| 2 | AfterChat 在不在 | 管理器面板里能看到 `AfterChat — LLM Chat Exporter`，状态为「启用」 | 回第 2 节点 AfterChat 链接；装完在面板里手动启用 |
| 3 | 页面按钮出没出 | 打开已登录的豆包会话，按 `Ctrl+F5` 强刷，右下角出现白色圆形按钮 | 检查管理器开关、AfterChat 是否启用、MV3「允许运行用户脚本」是否打开；再强刷 |
| 4 | 导出有没有落盘 | 点一次按钮，浏览器下载记录出现 `.md`；文件最终不是 `.crdownload` | 看第 4 节「下载卡住」 |
| 5 | 登录态对不对 | 浏览器里打开的是你日常已登录的豆包/DeepSeek，不是桌面客户端的内嵌浏览器 | 换回本机日常浏览器重新登录；不要用 IAB |

## 4. 导出按钮没出现：停，不进入下一步

如果页面右下角没有白色圆形按钮，不要继续跑入库。先打印/看到这个状态：

```text
EXPORT_BUTTON_MISSING
```

然后由本人手动做 4 件事：

1. 打开 `edge://extensions`，确认 Tampermonkey 或 ScriptCat 是启用状态；
2. 在管理器面板里确认 AfterChat 是「启用」，不是灰色；
3. 回到豆包会话页，按 `Ctrl+F5` 强刷；
4. 看右下角有没有白色圆形按钮；有就手动点导出。

导出成功后，由本人按 `Enter` 或输入 `continue`，才进入入库。没有真实 `.md`/`.zip` 落盘，就一直停在这里。

对应门禁命令：

```powershell
python -X utf8 scripts/10_export_gate.py --raw work/raw/afterchat --download-dir "D:\eage下载"
```

## 5. 下载卡住 / 一直 `.crdownload` 怎么办

AfterChat 用的是浏览器原生下载（`@grant none`），所以它完全遵守浏览器的下载设置：

- 如果开了「下载前询问保存位置」，会出现“打开 / 另存为 / 保存”的确认；**必须你本人点**，Agent 碰不到系统弹窗。
- 如果点完仍停在 `.crdownload`，先等 3–5 秒，再看文件大小是否停止增长；然后用 `Ctrl+J` 打开下载页确认状态。
- 产品侧不另做接收后台；正确做法是：
  1. 把浏览器下载目录设成固定目录（例如 `D:\XH-Downloads`）；
  2. 关掉「下载前询问保存位置」，或由本人在弹窗里点保存；
  3. 仍失败就停止，把 `Ctrl+J` 截图和 `.crdownload` 路径交给维护者，不要猜“已经导出成功”。

已查清的一种情况：Edge 下载历史记录 `state=4 INTERRUPTED`、`interrupt_reason=50 CRASH`，字节收满但收尾改名崩了，不是安全拦截。此时可以用恢复脚本生成 `.md` 副本，不删除原文件：

```powershell
python -X utf8 scripts/11_finalize_download.py --source-dir "D:\eage下载" --target-dir work/raw/afterchat --stable-seconds 3
```

这是恢复，不是“浏览器已经修好”。换机器仍可能复现。

## 6. 浏览器控制能力，别混在一起

| 组件 | 能做什么 | 不能做什么 |
|---|---|---|
| Tampermonkey / ScriptCat | 运行 AfterChat 这类用户脚本 | 本身不导出聊天，也不等于能控制浏览器 |
| AfterChat | 读当前会话 / 列表页，生成 `.md` 或 `.zip` | 不能切标签、不能点系统“另存为”、不能后台常驻 |
| sctl Browser + sctl | 管标签页、点击/填表/截图、读 console/network、开 CDP 给 Playwright/Puppeteer | 需要安装扩展 + CLI 配对；高权限，必须信任 |
| Chrome DevTools / Playwright | Agent 侧页面自动化；可复用登录态（需 CDP/连接） | 普通用户开箱即用程度低，需要开发环境 |
| Computer Use | 像人一样点桌面/浏览器窗口 | 依赖本机屏幕和窗口，不适合作为批量发布路径 |

**一句话**：AfterChat 是“导出工人”，不是“浏览器控制器”。你要让 Agent 真的动浏览器，必须另装 sctl Browser（或 Playwright/Chrome DevTools）；只装 AfterChat 只能导出，不能控制。

## 7. 缺件时的硬门禁

```text
没有脚本管理器 → 停止。给 Tampermonkey / ScriptCat 直达链接。
有管理器、没有 AfterChat → 停止。给 GreasyFork / raw 直装链接。
有 AfterChat、没启用 → 停止。要求在管理器面板里启用。
没登录态 → 停止。要求在本机日常浏览器登录。
下载目录不可写 → 停止。要求换目录或修权限。
```

不要做这三件事：

1. 不要自建一个“接收聊天内容”的后台服务来绕过扩展。
2. 不要把 DOM 兜底导出写成“对外发布路径”；DOM 只适合内部开发和临时救急。
3. 不要在用户拒绝安装后继续跑全流程，然后把失败算到“模型不行”。

## 8. 给维护者的自检命令

```powershell
python -X utf8 scripts/00_env_check.py --browser edge --dry-run
```

输出 `ENV_OK` 才能继续；输出 `ENV_BLOCKED` 时按提示补齐，不要继续。
