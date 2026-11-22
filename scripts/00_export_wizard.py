#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 2 Assistant: Consent-gated ScriptCat (脚本猫) export extension installer & MV3 switch guide."""

from __future__ import annotations

import argparse
import json
import pathlib
import urllib.request
import webbrowser
from typing import Callable

EXTENSION_URLS = {
    "edge": "https://microsoftedge.microsoft.com/addons/detail/liilgpjgabokdklappibcjfablkpcekh",
    "chrome": "https://chromewebstore.google.com/detail/hompjdfbfoggjbeebconmlijpelpfapo",
    "site": "https://scriptcat.org",
    "docs": "https://docs.scriptcat.org",
    "releases": "https://github.com/scriptscat/scriptcat/releases",
}

# Issue #11: ScriptCat is only the engine. AfterChat is the worker that actually
# exports conversations; installing ScriptCat alone reproduces the "clicked but
# nothing happened" dead end described in #7.
AFTERCHAT_URL = "https://greasyfork.org/zh-CN/scripts/589622-afterchat-llm-chat-exporter"

MV3_SWITCH_CHECKLIST = [
    "1. 打开扩展管理页：Edge 访问 edge://extensions  ｜ Chrome 访问 chrome://extensions",
    "2. 打开右上角「开发者模式（Developer Mode）」总开关",
    "3. 找到「脚本猫（ScriptCat）」，点击「扩展详细信息 / 详情（Details）」",
    "4. 开启「允许运行用户脚本（Allow User Scripts）」与「允许访问文件网址（Allow access to file URLs）」",
    "5. 回到 AI 对话网页按 Ctrl+F5 强刷新；此时只装了引擎，页面还不会有导出按钮（下一步装工人）",
]

AFTERCHAT_INSTALL_CHECKLIST = [
    "6. 再装「用户脚本（工人）」AfterChat：打开 " + AFTERCHAT_URL + " → 点「安装此脚本」→ 确认",
    "7. 回到任意 AI 对话页按 Ctrl+F5；右下角出现白色圆形下载按钮 = 已激活。没有按钮：先确认脚本管理器里 AfterChat 处于「启用」状态，再强刷几次",
]

GITHUB_LATEST_API = "https://api.github.com/repos/scriptscat/scriptcat/releases/latest"


def confirm_action(prompt: str, auto_yes: bool = False, input_fn: Callable[[str], str] = input) -> bool:
    """Require explicit user consent before opening external store pages or downloading extension packages."""
    if auto_yes:
        return True
    try:
        answer = input_fn(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes", "是", "确认"}


def download_latest_release(dest_dir: pathlib.Path, dry_run: bool = False) -> pathlib.Path | None:
    """Download official ScriptCat release archive from GitHub Releases into dest_dir."""
    if dry_run:
        print(f"[DRY-RUN] 将查询官方 API {GITHUB_LATEST_API} 并下载扩展包至 {dest_dir}")
        return None

    req = urllib.request.Request(GITHUB_LATEST_API, headers={"User-Agent": "XH-Dossier-Export-Wizard"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        release = json.loads(resp.read().decode("utf-8"))

    assets = release.get("assets", [])
    pick = next((a for a in assets if str(a.get("name", "")).endswith((".zip", ".crx"))), None)
    if not pick:
        raise RuntimeError("未在 ScriptCat 最新 Release 中找到 .zip/.crx 资源，请改用官方商店安装。")

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / str(pick["name"])
    dl_req = urllib.request.Request(pick["browser_download_url"], headers={"User-Agent": "XH-Dossier-Export-Wizard"})
    with urllib.request.urlopen(dl_req, timeout=60) as dl_resp:
        out_file.write_bytes(dl_resp.read())
    return out_file


def run_wizard(
    browser: str = "edge",
    download_release: bool = False,
    auto_yes: bool = False,
    dry_run: bool = False,
    dest_dir: pathlib.Path | None = None,
    input_fn: Callable[[str], str] = input,
    open_url_fn: Callable[[str], bool] = webbrowser.open,
    open_afterchat: bool = True,
) -> dict[str, object]:
    """Run guided ScriptCat installation + AfterChat worker install with explicit consent."""
    target_url = EXTENSION_URLS.get(browser, EXTENSION_URLS["site"])
    target_dir = dest_dir or pathlib.Path("work") / "extensions"

    print("=== ScriptCat（脚本猫）+ AfterChat 导出向导 ===")
    print(f"- 官方主页：{EXTENSION_URLS['site']}  ｜ 文档：{EXTENSION_URLS['docs']}")
    print(f"- 引擎商店（{browser}）：{target_url}")
    print(f"- 开源发布页：{EXTENSION_URLS['releases']}")
    print(f"- 工人脚本（AfterChat）：{AFTERCHAT_URL}")
    print("\n【第 1 关：安装引擎 ScriptCat 后必开的 5 步】")
    for step in MV3_SWITCH_CHECKLIST:
        print(" ", step)
    print("\n【第 2 关：装工人 AfterChat，否则扩展本身导不出任何东西】")
    for step in AFTERCHAT_INSTALL_CHECKLIST:
        print(" ", step)

    if download_release:
        action_desc = "是否由脚本下载 ScriptCat 官方开源压缩包"
    elif open_afterchat:
        action_desc = f"是否由脚本在浏览器中打开 {browser} 的 ScriptCat 商店页和 AfterChat 安装页"
    else:
        action_desc = f"是否由脚本在浏览器中打开 {browser} 的 ScriptCat 商店页"
    if not confirm_action(action_desc, auto_yes=auto_yes, input_fn=input_fn):
        print("WIZARD_DECLINED: 未获确认，不自动打开网页或下载文件。你可随时手动复制上方官方链接前往安装。")
        return {
            "consented": False,
            "url": target_url,
            "afterchat_url": AFTERCHAT_URL,
            "downloaded": None,
            "afterchat_opened": False,
        }

    if download_release:
        downloaded = download_latest_release(target_dir, dry_run=dry_run)
        if downloaded is not None:
            print(f"DOWNLOAD_OK: {downloaded}")
        print(f"AFTERCHAT_MANUAL: 请手动打开 {AFTERCHAT_URL} 安装工人脚本")
        return {
            "consented": True,
            "url": target_url,
            "afterchat_url": AFTERCHAT_URL,
            "downloaded": str(downloaded) if downloaded else None,
            "afterchat_opened": False,
        }

    if dry_run:
        print(f"[DRY-RUN] 将调用浏览器打开：{target_url}")
        if open_afterchat:
            print(f"[DRY-RUN] 将调用浏览器打开：{AFTERCHAT_URL}")
    else:
        open_url_fn(target_url)
        print(f"OPENED_OK: {target_url}")
        if open_afterchat:
            open_url_fn(AFTERCHAT_URL)
            print(f"OPENED_OK: {AFTERCHAT_URL}")
    return {
        "consented": True,
        "url": target_url,
        "afterchat_url": AFTERCHAT_URL,
        "downloaded": None,
        "afterchat_opened": bool(open_afterchat and not dry_run),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Consent-gated ScriptCat export extension setup wizard.")
    parser.add_argument("--browser", choices=["edge", "chrome", "site"], default="edge", help="Target store or official site")
    parser.add_argument("--download-release", action="store_true", help="Download official GitHub release archive instead of opening store")
    parser.add_argument("--yes", action="store_true", help="Confirm consent non-interactively")
    parser.add_argument("--dry-run", action="store_true", help="Preview links and actions without network/browser side effects")
    parser.add_argument("--no-afterchat", action="store_true", help="Do not open the AfterChat userscript page after consent")
    parser.add_argument("--dest", type=pathlib.Path, default=pathlib.Path("work") / "extensions", help="Download folder")
    args = parser.parse_args()

    result = run_wizard(
        browser=args.browser,
        download_release=args.download_release,
        auto_yes=args.yes,
        dry_run=args.dry_run,
        dest_dir=args.dest,
        open_afterchat=not args.no_afterchat,
    )
    # Issue #19: a declined consent is not an installed extension. Returning 0
    # made non-interactive callers proceed to export and hit the "no button" dead end.
    return 0 if result.get("consented") else 1


if __name__ == "__main__":
    raise SystemExit(main())
