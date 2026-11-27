#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Export stage gate.

No export button / no landed file -> stop. Do not continue to ingest.

This is deliberately interactive: the user must finish the browser action and
press Enter. The agent must not auto-continue on an empty export.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time


def landed_files(raw_dir: pathlib.Path) -> list[pathlib.Path]:
    if not raw_dir.is_dir():
        return []
    return sorted(
        p for p in raw_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".json", ".jsonl", ".txt", ".zip"}
    )


def partial_files(download_dir: pathlib.Path | None) -> list[pathlib.Path]:
    if download_dir is None or not download_dir.is_dir():
        return []
    return sorted(download_dir.rglob("*.crdownload"))


def manual_steps() -> str:
    return "\n".join([
        "请你手动做 4 件事：",
        "1. 打开 edge://extensions，确认 Tampermonkey 或 ScriptCat 是启用状态；",
        "2. 在管理器面板里确认 AfterChat 是「启用」，不是灰色；",
        "3. 回到豆包会话页，按 Ctrl+F5 强刷；",
        "4. 看右下角有没有白色圆形按钮；有就手动点导出。",
        "",
        "导出成功后，按 Enter 或输入 continue，才进入入库。",
        "没有 .md/.zip 落盘，就一直停在这里。",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate S2 export before S3 ingest.")
    parser.add_argument("--raw", type=pathlib.Path, default=pathlib.Path("work/raw"),
                        help="raw export directory that must contain a landed file")
    parser.add_argument("--download-dir", type=pathlib.Path, default=None,
                        help="browser download dir to check for .crdownload")
    parser.add_argument("--wait-confirm", action="store_true",
                        help="wait for the user to press Enter after manual export")
    parser.add_argument("--wait-seconds", type=int, default=0,
                        help="poll raw dir for N seconds before declaring missing")
    args = parser.parse_args()

    raw_dir = args.raw.expanduser().resolve()
    # P7: a missing directory is not the same as "the export button is missing".
    # The old code collapsed both into EXPORT_BUTTON_MISSING and sent the user
    # to click a button that was never the problem.
    if not raw_dir.is_dir():
        print("EXPORT_DIR_MISSING")
        print(f"路径不存在：{raw_dir}")
        print("先确认导出目录/挂载盘是否正确；需要时创建目录后重跑：")
        print(f'  mkdir "{raw_dir}"')
        print("这一步只检查落盘，不会替你点浏览器导出。")
        return 2

    deadline = time.time() + max(0, args.wait_seconds)
    while True:
        landed = landed_files(raw_dir)
        if landed:
            print(f"EXPORT_OK {raw_dir} files={len(landed)}")
            for path in landed[:5]:
                print(f"  - {path.name} ({path.stat().st_size} bytes)")
            return 0
        if time.time() >= deadline:
            break
        time.sleep(2)

    partials = partial_files(args.download_dir)
    if partials:
        print("DOWNLOAD_INTERRUPTED")
        print("浏览器下载停在 .crdownload，不能直接当 .md 用。")
        for path in partials[:5]:
            print(f"  - {path} ({path.stat().st_size} bytes)")
        print("先等内容完整，再由本人保存/改名；或跑 scripts/11_finalize_download.py。")
        print(manual_steps())
        return 1

    print("EXPORT_BUTTON_MISSING")
    print(manual_steps())
    if args.wait_confirm:
        try:
            answer = input("> ").strip().lower()
        except EOFError:
            answer = ""
        if answer in {"", "continue", "c", "继续", "是", "y", "yes"}:
            landed = landed_files(raw_dir)
            if landed:
                print(f"EXPORT_OK_AFTER_MANUAL {raw_dir} files={len(landed)}")
                return 0
            print("EXPORT_FILE_MISSING: 仍然没有真实 .md/.zip；继续停。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
