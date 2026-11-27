#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent map must stay complete: stages, commands, dirs, blockers, pointers."""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_agent_map_json_schema():
    data = json.loads((ROOT / "docs" / "agent-map.json").read_text(encoding="utf-8"))
    assert data["schema"] == "xh-agent-map-v1"
    assert data["core_priority"]["contract"] == "docs/core-reflow.md"
    stages = data["stages"]
    assert [s["id"] for s in stages] == [f"S{i}" for i in range(8)]
    for stage in stages:
        assert stage["goal"] and stage["command"] and stage["success"]
        assert isinstance(stage["outputs"], list)
        assert isinstance(stage["on_fail"], list) and stage["on_fail"]


def test_agent_map_markdown_links_and_commands():
    md = (ROOT / "AGENT_MAP.md").read_text(encoding="utf-8")
    for token in ("S0", "S7", "AGENT_START_HERE.md", "scripts/xh.py",
                  "SIGNING_KEY_MISSING", "BLIND_FAIL", "EXPORT_DIR_MISSING",
                  "docs/core-reflow.md", "上下文 → 带证据记忆 → 核心文件"):
        assert token in md
    assert "python -X utf8 scripts/xh.py doctor" in md
    assert "python -X utf8 scripts/xh.py build" in md


def test_start_here_and_agents_point_to_map():
    start = (ROOT / "AGENT_START_HERE.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "AGENT_MAP.md" in start
    assert "AGENT_MAP.md" in agents


def test_every_stage_command_is_mentioned():
    data = json.loads((ROOT / "docs" / "agent-map.json").read_text(encoding="utf-8"))
    md = (ROOT / "AGENT_MAP.md").read_text(encoding="utf-8")
    for stage in data["stages"]:
        # S1/S2 commands are skill/manual paths, not shell one-liners; the map
        # still names both stages and their entry files.
        if stage["id"] in ("S1", "S2"):
            continue
        first = stage["command"].split(";")[0].strip()
        assert first in md or stage["id"] == "S1"
