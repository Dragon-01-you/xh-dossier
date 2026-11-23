# -*- coding: utf-8 -*-
"""Regression tests for issue #55.

The doctor must tell two cases apart:
  (A) templates are really absent from the checkout;
  (B) templates are present, but their filenames are mojibake left behind by an
      extractor that ignored the zip UTF-8 flag (e.g. Info-ZIP UnZip 6.00).

Case B must NOT be reported as "missing templates"; it needs an actionable
encoding-corruption message with re-extraction commands.
"""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

mod_doctor = import_module("00_doctor")


def _cp437_mojibake(name: str) -> str:
    """Simulate what an old extractor does: UTF-8 bytes decoded as CP437."""
    return name.encode("utf-8").decode("cp437")


def _make_root(tmp_path: pathlib.Path, garbled: bool) -> pathlib.Path:
    root = tmp_path / "fake_repo"
    (root / "scripts").mkdir(parents=True)
    (root / "templates").mkdir(parents=True)
    for script in mod_doctor.REQUIRED_SCRIPTS:
        (root / script).write_text("# placeholder\n", encoding="utf-8")
    if garbled:
        for rel in mod_doctor.REQUIRED_TEMPLATES:
            base = pathlib.PurePosixPath(rel).name
            if base == "AGENTS.md":
                (root / rel).write_text("# ok\n", encoding="utf-8")
            else:
                bad = _cp437_mojibake(base)
                (root / "templates" / bad).write_text("# body\n", encoding="utf-8")
    return root


def test_truly_missing_templates_report_missing(tmp_path: pathlib.Path) -> None:
    """Case A: nothing in templates/ -> plain 'missing files' message."""
    root = _make_root(tmp_path, garbled=False)
    with pytest.raises(mod_doctor.DoctorError) as exc:
        mod_doctor.check_files(root)
    msg = str(exc.value)
    assert "缺少必需文件" in msg
    assert "编码损坏" not in msg


def test_garbled_template_names_report_encoding_not_missing(tmp_path: pathlib.Path) -> None:
    """Case B: files exist under mojibake names -> encoding-corruption message."""
    root = _make_root(tmp_path, garbled=True)
    with pytest.raises(mod_doctor.DoctorError) as exc:
        mod_doctor.check_files(root)
    msg = str(exc.value)
    assert "编码损坏" in msg
    assert "缺少必需文件" not in msg
    # The expected canonical name is named in the advice.
    assert "00-总入口索引.md" in msg
