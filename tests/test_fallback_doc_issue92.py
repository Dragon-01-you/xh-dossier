#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Issue #92: the local POST receiver is gone; the two replacement landing
links (extension native download / Agent DOM write) must be documented with
their unverified boundary, and no receiver code/port may remain in scripts/.
"""

from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
fallback = (REPO / "docs" / "fallback-dom-export.md").read_text(encoding="utf-8")
guide = (REPO / "docs" / "02-multi-platform-export.md").read_text(encoding="utf-8")


def test_fallback_doc_names_both_replacement_links() -> None:
    assert "替代链路 A" in fallback and "扩展原生下载" in fallback
    assert "替代链路 B" in fallback and "Agent 读 DOM" in fallback
    assert "work/raw" in fallback


def test_fallback_doc_states_unverified_boundary() -> None:
    assert "未真机验证边界" in fallback or "未在浏览器验证" in fallback
    assert "UNVERIFIED" in fallback
    assert "Ctrl+J" in fallback


def test_guide_links_back_to_fallback_section_7() -> None:
    assert "fallback-dom-export.md" in guide
    assert "#92" in guide


def test_no_local_receiver_residue_in_scripts() -> None:
    residue = []
    for script in (REPO / "scripts").glob("*.py"):
        text = script.read_text(encoding="utf-8", errors="replace")
        for token in ("127.0.0.1", "localhost:8765", "8765", "receiver"):
            if token in text:
                residue.append((script.name, token))
    assert residue == [], residue
