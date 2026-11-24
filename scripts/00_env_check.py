#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Onboarding environment gate for XH-Dossier.

Checks the things a stranger must have before the export step:
browser, userscript manager, AfterChat, a logged-in AI site, and a writable
download directory. Missing pieces are blockers, not warnings.

The checker never installs anything silently. It prints official links and,
only with explicit consent, opens them in the browser.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

LINKS = {
    "tampermonkey_site": "https://www.tampermonkey.net/",
    "tampermonkey_edge": "https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd",
    "tampermonkey_chrome": "https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo",
    "scriptcat_edge": "https://microsoftedge.microsoft.com/addons/detail/%E8%84%9A%E6%9C%AC%E7%8C%AB/liilgpjgabokdklappibcjfablkpcekh",
    "scriptcat_chrome": "https://chromewebstore.google.com/detail/hompjdfbfoggjbeebconmlijpelpfapo",
    "afterchat_greasyfork": "https://greasyfork.org/en/scripts/589622-afterchat-llm-chat-exporter",
    "afterchat_raw": "https://raw.githubusercontent.com/AfterThink/AfterChat-Script/main/afterchat.user.js",
    "afterchat_github": "https://github.com/AfterThink/AfterChat-Script",
    "sctl_browser_edge": "https://microsoftedge.microsoft.com/addons/detail/sctl-browser/nbmnkdfbjdhbdjjffgkocfdkemockepa",
    "sctl_github": "https://github.com/scriptscat/sctl",
    "sctl_docs": "https://docs.scriptcat.org/en/docs/use/sctl-browser/",
}

MANAGER_IDS = {
    "tampermonkey": "iikmkjmpaadaobahmlepeloendndfphd",
    "scriptcat": "liilgpjgabokdklappibcjfablkpcekh",
}

COOKIE_HINTS = (
    "doubao.com",
    "deepseek.com",
    "chatgpt.com",
    "claude.ai",
    "gemini.google.com",
    "kimi.com",
    "qwen.ai",
    "yuanbao.tencent.com",
)

BROWSER_LAYOUT = {
    "edge": ("Microsoft", "Edge", "msedge.exe"),
    "chrome": ("Google", "Chrome", "chrome.exe"),
}


def _local_appdata() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path.home() / "AppData" / "Local"


def browser_executable(browser: str) -> Path | None:
    """Return the first existing executable for the selected browser."""
    vendor, product, exe = BROWSER_LAYOUT[browser]
    roots = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
    ]
    for root in roots:
        candidate = root / vendor / product / "Application" / exe
        if candidate.exists():
            return candidate
    found = shutil.which(exe)
    return Path(found) if found else None


def browser_data_dir(browser: str) -> Path:
    vendor, product, _ = BROWSER_LAYOUT[browser]
    return _local_appdata() / vendor / product / "User Data"


def profile_dirs(browser: str) -> list[Path]:
    base = browser_data_dir(browser)
    if not base.exists():
        return []
    profiles: list[Path] = []
    default = base / "Default"
    if default.exists():
        profiles.append(default)
    profiles.extend(sorted(p for p in base.glob("Profile *") if p.is_dir()))
    return profiles


def extension_present(profile: Path, extension_id: str) -> bool:
    candidates = [
        profile / "Extensions" / extension_id,
        profile / "Local Extension Settings" / extension_id,
        profile / "Extension State" / extension_id,
    ]
    return any(path.exists() for path in candidates)


def detect_managers(browser: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for profile in profile_dirs(browser):
        for name, extension_id in MANAGER_IDS.items():
            if extension_present(profile, extension_id):
                found.append({"name": name, "profile": profile.name, "id": extension_id})
    return found


def _contains_text(path: Path, needle: bytes, max_bytes: int = 48 * 1024 * 1024) -> bool:
    try:
        if path.stat().st_size > max_bytes:
            return False
        with path.open("rb") as handle:
            return needle in handle.read()
    except OSError:
        return False


def detect_afterchat(browser: str) -> dict[str, Any]:
    """Best-effort detection: AfterChat is a userscript stored inside the manager's LevelDB."""
    hits: list[str] = []
    for profile in profile_dirs(browser):
        for manager_name, extension_id in MANAGER_IDS.items():
            storage = profile / "Local Extension Settings" / extension_id
            if not storage.exists():
                continue
            for candidate in storage.rglob("*"):
                if not candidate.is_file() or candidate.suffix.lower() not in {".ldb", ".log", ".json"}:
                    continue
                if _contains_text(candidate, b"AfterChat"):
                    hits.append(f"{profile.name}/{manager_name}/{candidate.name}")
    return {"found": bool(hits), "hits": hits}


def _cookie_path(profile: Path) -> Path | None:
    for candidate in (profile / "Network" / "Cookies", profile / "Cookies"):
        if candidate.exists():
            return candidate
    return None


def detect_login(browser: str) -> dict[str, Any]:
    hosts: set[str] = set()
    errors: list[str] = []
    for profile in profile_dirs(browser):
        cookie_path = _cookie_path(profile)
        if cookie_path is None:
            continue
        temp_dir = Path(tempfile.mkdtemp(prefix="xh_cookie_"))
        temp_db = temp_dir / "Cookies"
        try:
            # Edge keeps an exclusive lock on its live cookie DB; copy first, then query.
            shutil.copy2(cookie_path, temp_db)
            con = sqlite3.connect(temp_db, timeout=5)
            rows = con.execute("SELECT DISTINCT host_key FROM cookies").fetchall()
            hosts.update(str(row[0]) for row in rows if row and row[0])
            con.close()
        except (OSError, sqlite3.Error) as exc:
            errors.append(f"{profile.name}: {exc}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    matched = sorted(h for h in hosts if any(hint in h for hint in COOKIE_HINTS))
    return {"found": bool(matched), "hosts": matched, "errors": errors}


def _read_preferences(profile: Path) -> dict[str, Any]:
    path = profile / "Preferences"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}


def download_settings(browser: str, override: Path | None = None) -> dict[str, Any]:
    default_dir = override or (Path.home() / "Downloads")
    prompt_for_download = False
    source = "override" if override else "default"
    for profile in profile_dirs(browser):
        prefs = _read_preferences(profile)
        download = prefs.get("download") or {}
        configured = download.get("default_directory")
        if configured and not override:
            default_dir = Path(str(configured)).expanduser()
            source = f"{profile.name}/Preferences"
        prompt_for_download = bool(download.get("prompt_for_download", False))
        break
    return {
        "directory": default_dir,
        "prompt_for_download": prompt_for_download,
        "source": source,
    }


def writable_directory(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "目录不存在"
    if not path.is_dir():
        return False, "不是目录"
    try:
        fd, probe = tempfile.mkstemp(prefix=".xh_write_test_", dir=str(path))
        os.close(fd)
        Path(probe).unlink(missing_ok=True)
        return True, "可写"
    except OSError as exc:
        return False, f"不可写：{exc}"


def _item(name: str, status: str, detail: str, link: str | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail, "link": link}


def build_report(browser: str, download_dir: Path | None = None, confirm_login: bool = False) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    items.append(_item("os", "ok", f"{platform.system()} {platform.release()}"))

    executable = browser_executable(browser)
    if executable:
        items.append(_item("browser", "ok", str(executable)))
    else:
        items.append(_item("browser", "missing", f"未找到 {browser} 可执行文件", LINKS["tampermonkey_site"]))

    managers = detect_managers(browser)
    if managers:
        names = ", ".join(sorted({m["name"] for m in managers}))
        profiles = ", ".join(sorted({m["profile"] for m in managers}))
        items.append(_item("userscript_manager", "ok", f"检测到 {names}（{profiles}）"))
    else:
        items.append(
            _item(
                "userscript_manager",
                "missing",
                "未检测到 Tampermonkey / ScriptCat；请到 edge://extensions 或 chrome://extensions 确认",
                LINKS[f"tampermonkey_{browser}"],
            )
        )

    afterchat = detect_afterchat(browser)
    if afterchat["found"]:
        items.append(_item("afterchat", "ok", "检测到 AfterChat 存储：" + "; ".join(afterchat["hits"][:3])))
    else:
        items.append(
            _item(
                "afterchat",
                "missing",
                "未检测到 AfterChat；若已安装请打开管理器面板确认状态为「启用」",
                LINKS["afterchat_greasyfork"],
            )
        )

    login = detect_login(browser)
    if login["found"]:
        items.append(_item("login", "ok", "检测到登录站点 Cookie：" + ", ".join(login["hosts"][:5])))
    elif confirm_login:
        items.append(_item("login", "ok", "已由本人确认：日常浏览器已登录目标 AI 站点"))
    elif login["errors"]:
        items.append(
            _item(
                "login",
                "unverified",
                "无法读取浏览器 Cookie 数据库（浏览器正在占用）；请打开目标站点手动确认已登录，再重跑或加 --confirm-login",
                "https://www.doubao.com/",
            )
        )
    else:
        items.append(
            _item(
                "login",
                "missing",
                "未检测到豆包/DeepSeek/ChatGPT 等登录 Cookie；请在本机日常浏览器登录",
                "https://www.doubao.com/",
            )
        )

    settings = download_settings(browser, override=download_dir)
    directory = settings["directory"]
    ok, detail = writable_directory(directory)
    if ok:
        prompt = "；浏览器会弹「另存为」确认，需本人点保存" if settings["prompt_for_download"] else ""
        items.append(_item("download_dir", "ok", f"{directory}（{detail}{prompt}）"))
    else:
        items.append(_item("download_dir", "missing", f"{directory}：{detail}", None))

    sctl = shutil.which("sctl")
    items.append(
        _item(
            "browser_control",
            "info",
            "sctl CLI 已安装；未安装也不影响导出" if sctl else "未安装 sctl；只有需要 Agent 控制浏览器时才需要",
            LINKS["sctl_browser_edge"],
        )
    )

    blockers = [item for item in items if item["status"] in {"missing", "unverified"}]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "browser": browser,
        "items": items,
        "blocked": bool(blockers),
        "blockers": [item["name"] for item in blockers],
    }


def print_human(report: dict[str, Any]) -> None:
    print("=== XH-Dossier onboarding environment check ===")
    for item in report["items"]:
        status = item["status"].upper()
        print(f"[{status:7}] {item['name']}: {item['detail']}")
        if item["status"] in {"missing", "unverified"} and item.get("link"):
            print(f"          link: {item['link']}")
    print()
    if report["blocked"]:
        print("ENV_BLOCKED: " + ", ".join(report["blockers"]))
        print("这是必要步骤：缺件时不要继续导出，也不要自建后台。按上面的链接装好后再跑。")
    else:
        print("ENV_OK")


def open_missing_links(report: dict[str, Any], auto_yes: bool, open_url: Callable[[str], bool] = webbrowser.open) -> None:
    links = [item["link"] for item in report["items"] if item["status"] in {"missing", "unverified"} and item.get("link")]
    if not links:
        return
    if not auto_yes:
        answer = input("是否现在打开缺失组件的官方安装页？[y/N]: ").strip().lower()
        if answer not in {"y", "yes", "是", "确认"}:
            print("OPEN_DECLINED: 未打开浏览器；链接已打印在上方。")
            return
    for link in links:
        open_url(link)
        print(f"OPENED_OK: {link}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check XH-Dossier onboarding prerequisites before export.")
    parser.add_argument("--browser", choices=["edge", "chrome"], default="edge")
    parser.add_argument("--download-dir", type=Path, default=None, help="Override the download directory to check")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--confirm-login", action="store_true", help="本人确认已登录目标 AI 站点，跳过 Cookie 自动探测")
    parser.add_argument("--dry-run", action="store_true", help="Only check and print; never open a browser")
    parser.add_argument("--open-missing", action="store_true", help="Open official install pages for missing components")
    parser.add_argument("--yes", action="store_true", help="Skip the open confirmation (use with --open-missing)")
    args = parser.parse_args()

    report = build_report(args.browser, download_dir=args.download_dir, confirm_login=args.confirm_login)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)

    if args.open_missing and not args.dry_run:
        open_missing_links(report, auto_yes=args.yes)

    return 1 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
