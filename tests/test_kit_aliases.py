#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Real-world 6-file kit naming and inline-code compatibility tests."""

import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

mod = importlib.import_module("03_validate_kit")


def _write_kit(tmp_path: pathlib.Path) -> pathlib.Path:
    kit = tmp_path / "kit"
    kit.mkdir()
    bodies = {
        "AGENTS.md": "# 合作站位\n\n这是给 AI 看的合作规矩。遇到不确定时先问本人，不编造事实，不把 AI 的总结当成我的原话；先读原文，再下结论，遇到冲突以本人最终签字为准。这一段也用于测试，必须足够长，避免被 80 字门槛挡住。\n",
        "00-总入口索引.md": "# 总入口\n\n读取顺序：先读 AGENTS，再读 01、02、03、04。当前任务/<任务>/ 只是运行时目录变量，不是未填字段；外部知识库只读引用，不把旧摘要当新事实。\n",
        "01-身份与当前主线.md": "# 身份\n\n我是一个持续学习 Python 的个人开发者，当前主线是把 AI 工作流做成可复用的本地工具，并用真实项目验证；不追求看起来厉害，只追求能跑通、能复盘、能交接。\n",
        "02-核心判断准则.md": "# 判断\n\n先验证再下结论；不把提及时间当事件时间；不确定就标记待确认并回到原文核对，不拿高阶段标准压现在；先懂树干原理，再按按钮。这一段也用于测试，必须足够长，避免被 80 字门槛挡住。\n",
        "03-硬规则与表达黑话.md": "# 表达\n\n说人话，先给结论，再给证据；不堆术语，不用空洞的赋能闭环。遇到缩写先问清定义，不自行曲解；长任务拆成可验证的小步，每步给产物。这一段也用于测试，必须足够长，避免被 80 字门槛挡住。\n",
        "04-反面案例清单.md": "# 反例\n\n曾经把 AI 的总结当成自己的原话，后来改为只读 raw 原文并保留出处；没有原文的判断一律不进档案，宁可标待确认，也不编一个漂亮结论。这一段也用于测试，必须足够长，避免被 80 字门槛挡住。\n",
    }
    for name, body in bodies.items():
        (kit / name).write_text(body, encoding="utf-8")
    return kit


def test_real_04_alias_and_inline_runtime_variable(tmp_path: pathlib.Path) -> None:
    kit = _write_kit(tmp_path)
    ok, messages = mod.validate_kit(kit, strict=True)
    assert ok, messages


def test_missing_04_still_fails_when_neither_name_exists(tmp_path: pathlib.Path) -> None:
    kit = _write_kit(tmp_path)
    (kit / "04-反面案例清单.md").unlink()
    ok, messages = mod.validate_kit(kit, strict=True)
    assert not ok
    assert any("04-正反例避坑账.md" in message for message in messages)
