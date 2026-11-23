# -*- coding: utf-8 -*-
"""Issue #101 (Epic #75): the testing-environment method doc records the
home-edition Sandbox forensic conclusion and the system-preserving alternatives.
This is a method ticket: no product-code behavior change is asserted here.
"""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
doc = (REPO_ROOT / "docs" / "testing-environment.md").read_text(encoding="utf-8")


def test_forensic_facts_recorded():
    for token in ("Windows 10 Home China", "CoreCountrySpecific", "740", "Medium Mandatory Level"):
        assert token in doc, f"取证结论缺记录：{token}"
    # The home edition must be marked as unable to use Sandbox, not worked around
    # by disabling UAC or forcing elevation.
    assert "Windows Sandbox" in doc
    assert "不要求" in doc and "提权" in doc


def test_alternatives_without_changing_system():
    for token in ("净化 profile", "云主机", "临时目录"):
        assert token in doc, f"替代测试方法缺：{token}"
    # Boundary: the sanitized profile is not a sandbox isolation claim.
    assert "不是沙箱隔离" in doc


def test_doctor_boundary_documented():
    # Doctor intentionally does not gate on home edition; the doc must say so.
    assert "不" in doc and "家庭版" in doc
    assert "本票不改产品代码" in doc
