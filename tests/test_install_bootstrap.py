#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression: install.ps1 must consume bootstrap's reported interpreter path.

A real Doubao CLI run on 2026-11-24 exposed that bootstrap could find an existing
Python 3.11+ and print ``BOOTSTRAP_OK python=...`` while install.ps1 only checked
the portable candidate path, then falsely exited with INSTALL_FAIL.
"""

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
INSTALL = (REPO / "install.ps1").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")


def test_install_reads_bootstrap_reported_python_path():
    assert "BOOTSTRAP_OK python=" in INSTALL
    assert "$bootPy" in INSTALL
    assert "Test-Path -LiteralPath $bootPy" in INSTALL


def test_readme_documents_bootstrap_not_manual_only():
    assert "自动下载" in README
    assert "embeddable" in README
    assert "BOOTSTRAP_OK" in README
    assert "不需要先手工装 Python" in README
