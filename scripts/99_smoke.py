#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 0 冒烟测试（smoke）：在临时目录跑通 01 -> 02 -> 03 最小样例。

成功输出 SMOKE_OK（exit 0）；失败给人话错误 + SMOKE_FAIL（exit 2），不把 traceback 丢给用户。
不写仓库 work/ 目录，所有中间产物放在系统临时目录，跑完自动清理。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# 最小合法 kit：每份有具体事实/日期/案例，无占位符、无 PII、无 [待确认]。
MINIMAL_KIT = {
    "AGENTS.md": (
        "# AGENTS.md — 合作规矩\n\n"
        "## 站位\n先对齐目标，有逻辑漏洞直接拿事实与反例顶回来。2026-10-22 用户明确要求"
        "「先讲原理再给代码」，不要一上来就甩两百行脚本。\n\n"
        "## 表达\n先用白话讲清底层在干嘛，打一个生活比方，再给步骤，最后才贴代码。\n\n"
        "## 边界\n原始导出资料只读，摘要另存不覆盖原文；未经同意不替用户删改原件。\n"
    ),
    "00-总入口索引.md": (
        "# 00 总入口索引\n\n"
        "## 读取顺序\n先读 AGENTS.md，再依次读 01 身份与当前主线、02 核心判断准则、"
        "03 硬规则与表达黑话、04 正反例避坑账。\n\n"
        "## 平台地图\n网页端与本地端混用，导出原件一律进 raw 目录只读保存，不提前写摘要覆盖原文。"
        "只读参考堆与用户个人结论分开存放，不混读。\n"
    ),
    "01-身份与当前主线.md": (
        "# 01 身份与当前主线\n\n"
        "## 稳定事实\n对外统一称呼林墨，曾用名小墨，2026-10-22 起不再使用。\n\n"
        "## 当前主线\n把散落在多个聊天窗口的上下文收敛成六份可迁移的个人 Memory。"
        "卡点是每次新窗口都要重复解释，2026-11-03 记录过这一痛点。\n\n"
        "## 硬约束\n每天只有晚间一到两小时，先跑通闭环再考虑扩展。\n"
    ),
    "02-核心判断准则.md": (
        "# 02 核心判断准则\n\n"
        "## 优先顺序\n目标与真需求 → 方法骨架 → 具体招式 → 工具按钮，不先聊工具。\n\n"
        "## 完成标准\n内外双验收：发到真实环境跑通，本地测试全绿，且能合上屏幕用白话讲给新手听。\n\n"
        "## 拖延刹车\n单个工具卡点超过十五分钟就换路线或上报，不原地死循环。"
        "2026-10-12 曾因停在最后百分之十拖了四天。\n"
    ),
    "03-硬规则与表达黑话.md": (
        "# 03 硬规则与表达黑话\n\n"
        "## 红线\n原始导出资料只读不动，同一报错连试两次不通立刻换方案，不替用户重写代码。\n\n"
        "## 别名\n曾用名小墨，现统一称呼林墨，2026-10-22 起生效。\n\n"
        "## 语音错字\n用户用语音输入，画风常被识别错，真实本意是换个话题。"
        "遇到含混词先问一句，不静默脑补。\n"
    ),
    "04-正反例避坑账.md": (
        "# 04 正反例避坑账\n\n"
        "## 正例\n2026-10-28 开工前定死验收标准，一次只改一个文件，两小时交付，没有返工。\n\n"
        "## 反例\n2026-10-12 静态小工具停在最后百分之十改按钮对齐，拖了四天错过提交截止。"
        "另一个终端的 AI 把方向记成全职电商，而该副业早已砍掉。\n"
    ),
}


class SmokeError(Exception):
    """可预期的人话错误，直接转成 exit 2。"""


def run_step(name: str, argv: list[str], expect: str) -> None:
    proc = subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    combined = f"{proc.stdout or ''}{proc.stderr or ''}"
    if proc.returncode != 0 or expect not in combined:
        snippet = combined.strip().replace("\n", " | ")[:300]
        raise SmokeError(
            f"{name} 未通过：期望 {expect}，exit={proc.returncode}，输出：{snippet}"
        )
    print(f"[OK] {name} -> {expect}")


def run() -> None:
    if not (ROOT / "examples" / "sample_raw").is_dir():
        raise SmokeError("缺少 examples/sample_raw 最小样例，请确认仓库完整。")

    with tempfile.TemporaryDirectory(prefix="xh_smoke_") as tmp_name:
        tmp = pathlib.Path(tmp_name)
        db = tmp / "index.db"
        report = tmp / "backfill.md"
        kit = tmp / "kit"
        kit.mkdir()
        for filename, content in MINIMAL_KIT.items():
            (kit / filename).write_text(content, encoding="utf-8")

        run_step(
            "01 清洗索引",
            [PYTHON, "-X", "utf8", "scripts/01_clean_and_index.py",
             "--raw", "examples/sample_raw", "--db", str(db)],
            "INDEX_OK",
        )
        run_step(
            "02 四路匹配",
            [PYTHON, "-X", "utf8", "scripts/02_four_way_match.py",
             "--db", str(db), "--out", str(report)],
            "FOUR_WAY_OK",
        )
        run_step(
            "03 严格校验",
            [PYTHON, "-X", "utf8", "scripts/03_validate_kit.py",
             "--target", str(kit), "--strict"],
            "VALIDATE_OK",
        )


def main() -> int:
    try:
        run()
    except SmokeError as exc:
        print(f"SMOKE_FAIL: {exc}")
        return 2
    except Exception as exc:
        print(f"SMOKE_FAIL: 冒烟过程中出现未预期错误：{type(exc).__name__}: {exc}")
        return 2

    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
