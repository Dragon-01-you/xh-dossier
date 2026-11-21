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

MV3_SWITCH_CHECKLIST = [
    "1. 打开扩展管理页：Edge 访问 edge://extensions  ｜ Chrome 访问 chrome://extensions",
    "2. 打开右上角「开发者模式（Developer Mode）」总开关",
    "3. 找到「脚本猫（ScriptCat）」，点击「扩展详细信息 / 详情（Details）」",
    "4. 开启「允许运行用户脚本（Allow User Scripts）」与「允许访问文件网址（Allow access to file URLs）」",
    "5. 回到 AI 对话网页按 Ctrl+F5 强刷新，即可点击导出原件 .json / .md 放入 raw/",
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
) -> dict[str, object]:
    """Run guided ScriptCat installation with explicit user consent and MV3 switch checklist."""
    target_url = EXTENSION_URLS.get(browser, EXTENSION_URLS["site"])
    target_dir = dest_dir or pathlib.Path("work") / "extensions"

    print("=== ScriptCat（脚本猫）官方导出扩展向导 ===")
    print(f"- 官方主页：{EXTENSION_URLS['site']}  ｜ 文档：{EXTENSION_URLS['docs']}")
    print(f"- 官方商店（{browser}）：{target_url}")
    print(f"- 开源发布页：{EXTENSION_URLS['releases']}")
    print("\n【安装后必开 5 步浏览器开关清单】")
    for step in MV3_SWITCH_CHECKLIST:
        print(" ", step)

    action_desc = f"是否由脚本{'下载官方开源压缩包' if download_release else f'在浏览器中打开 {browser} 商店页面'}"
    if not confirm_action(action_desc, auto_yes=auto_yes, input_fn=input_fn):
        print("WIZARD_DECLINED: 未获确认，不自动打开网页或下载文件。你可随时手动复制上方官方链接前往安装。")
        return {"consented": False, "url": target_url, "downloaded": None}

    if download_release:
        downloaded = download_latest_release(target_dir, dry_run=dry_run)
        if downloaded is not None:
            print(f"DOWNLOAD_OK: {downloaded}")
        return {"consented": True, "url": target_url, "downloaded": str(downloaded) if downloaded else None}

    if dry_run:
        print(f"[DRY-RUN] 将调用浏览器打开：{target_url}")
    else:
        open_url_fn(target_url)
        print(f"OPENED_OK: {target_url}")
    return {"consented": True, "url": target_url, "downloaded": None}


def main() -> int:
    parser = argparse.ArgumentParser(description="Consent-gated ScriptCat export extension setup wizard.")
    parser.add_argument("--browser", choices=["edge", "chrome", "site"], default="edge", help="Target store or official site")
    parser.add_argument("--download-release", action="store_true", help="Download official GitHub release archive instead of opening store")
    parser.add_argument("--yes", action="store_true", help="Confirm consent non-interactively")
    parser.add_argument("--dry-run", action="store_true", help="Preview links and actions without network/browser side effects")
    parser.add_argument("--dest", type=pathlib.Path, default=pathlib.Path("work") / "extensions", help="Download folder")
    args = parser.parse_args()

    run_wizard(
        browser=args.browser,
        download_release=args.download_release,
        auto_yes=args.yes,
        dry_run=args.dry_run,
        dest_dir=args.dest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
