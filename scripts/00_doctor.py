#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 0 环境预检（doctor）。

面向普通用户 + 本地 Agent：确认 Python / SQLite FTS5+trigram / 工作目录 / 模板脚本是否齐全。
成功输出 DOCTOR_OK（exit 0）；失败给人话错误 + DOCTOR_FAIL（exit 2），不把 traceback 丢给用户。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sqlite3
import sys

MIN_PYTHON = (3, 11)
PROBE_TEXT = "你好世界hello"

REQUIRED_SCRIPTS = [
    "scripts/00_export_wizard.py",
    "scripts/01_clean_and_index.py",
    "scripts/02_four_way_match.py",
    "scripts/03_validate_kit.py",
    "scripts/99_smoke.py",
]
REQUIRED_TEMPLATES = [
    "templates/AGENTS.md",
    "templates/00-总入口索引.md",
    "templates/01-身份与当前主线.md",
    "templates/02-核心判断准则.md",
    "templates/03-硬规则与表达黑话.md",
    "templates/04-正反例避坑账.md",
]


class DoctorError(Exception):
    """可预期的人话错误，直接转成 exit 2。"""


def check_python() -> None:
    current = sys.version_info[:2]
    if current < MIN_PYTHON:
        raise DoctorError(
            f"Python 版本过低：需要 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}，"
            f"当前 {current[0]}.{current[1]}。请升级 Python 后重试。"
        )
    print(f"[OK] Python {current[0]}.{current[1]}（>= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}）")


def check_fts5_trigram() -> None:
    try:
        con = sqlite3.connect(":memory:")
        try:
            con.execute("CREATE VIRTUAL TABLE _doctor_fts USING fts5(body, tokenize='trigram')")
            con.execute("INSERT INTO _doctor_fts(body) VALUES (?)", (PROBE_TEXT,))
            match_hits = con.execute(
                "SELECT count(*) FROM _doctor_fts WHERE body MATCH ?", ("你好世",)
            ).fetchone()[0]
            like_hits = con.execute(
                "SELECT count(*) FROM _doctor_fts WHERE body LIKE ?", ("%你好%",)
            ).fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise DoctorError(
            f"SQLite FTS5/trigram 不可用：{exc}。"
            "请确认当前 Python 的 sqlite3 编译时启用了 FTS5。"
        ) from None
    if match_hits < 1 or like_hits < 1:
        raise DoctorError("SQLite FTS5/trigram 建表成功但查询无结果，索引能力异常。")
    print("[OK] SQLite FTS5 + trigram 真建表 / 插入 / 查询通过")


def check_root(root: pathlib.Path) -> None:
    if not root.exists():
        raise DoctorError(f"仓库根目录不存在：{root}。请用 --root 指向正确的仓库目录。")
    if not root.is_dir():
        raise DoctorError(f"仓库根路径不是目录：{root}。请用 --root 指向正确的仓库目录。")


def check_workdir(root: pathlib.Path) -> None:
    probe = root / f".doctor_write_test_{os.getpid()}"
    try:
        probe.write_text("doctor probe", encoding="utf-8")
        if not probe.is_file():
            raise OSError("探针文件未生成")
    except OSError as exc:
        raise DoctorError(
            f"工作目录不可写：{root}（{exc}）。请检查权限，或用 --root 指向可写目录。"
        ) from None
    finally:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
    print(f"[OK] 工作目录可写：{root}")


def check_files(root: pathlib.Path) -> None:
    missing = [
        rel for rel in REQUIRED_SCRIPTS + REQUIRED_TEMPLATES
        if not (root / rel).is_file()
    ]
    if missing:
        preview = "、".join(missing[:5])
        if len(missing) > 5:
            preview += "…"
        raise DoctorError(
            f"缺少必需文件：{preview}。请确认仓库完整，或重新获取发布包。"
        )
    print(f"[OK] 必需脚本 {len(REQUIRED_SCRIPTS)} 个 / 模板 {len(REQUIRED_TEMPLATES)} 份齐全")


def run(root: pathlib.Path) -> None:
    check_python()
    check_fts5_trigram()
    check_root(root)
    check_workdir(root)
    check_files(root)


def main() -> int:
    parser = argparse.ArgumentParser(description="XH-Dossier 环境预检（doctor）。")
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent.parent,
        help="仓库根目录（默认脚本所在目录的上一级）",
    )
    args = parser.parse_args()

    try:
        run(args.root)
    except DoctorError as exc:
        print(f"DOCTOR_FAIL: {exc}")
        return 2
    except Exception as exc:
        print(f"DOCTOR_FAIL: 预检过程中出现未预期错误：{type(exc).__name__}: {exc}")
        return 2

    print("DOCTOR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
