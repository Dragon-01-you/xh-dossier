# -*- coding: utf-8 -*-
"""Regression tests for ISSUE-M4-01 / T3: illegal UTF-8 must never be silently replaced."""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

mod_clean = import_module("01_clean_and_index")


def _illegal_bytes() -> bytes:
    return (
        "## 2026-01-01 测试\nUser: 正常文本".encode("utf-8")
        + b"\xff\xfe"
        + "\nAssistant: 后面文本".encode("utf-8")
    )


def test_clean_and_index_counts_illegal_utf8(tmp_path: pathlib.Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bad.md").write_bytes(_illegal_bytes())

    stats = mod_clean.clean_and_index(raw, tmp_path / "cold.db")

    assert stats["encoding_replaced_files"] == 1
    assert stats["encoding_replaced_chars"] >= 1
    assert stats["indexed"] >= 1  # record is still indexed, but with replacement text
    assert any(name == "bad.md" for name, _ in stats["encoding_replaced_detail"])


@pytest.mark.parametrize("filename,payload", [
    ("bad.json", b'{"role":"user","content":"ok \xff invalid","time":"2026-01-01"}'),
    ("bad.jsonl", b'{"role":"user","content":"ok \xff invalid","time":"2026-01-01"}\n'),
    ("bad.md", b"## 2026-01-01\nUser: ok \xff invalid"),
    ("bad.txt", b"## 2026-01-01\nUser: ok \xff invalid"),
])
def test_all_read_paths_detect_illegal_utf8(tmp_path: pathlib.Path, filename: str, payload: bytes) -> None:
    """All three read_text call sites (.json/.jsonl/.md/.txt) must detect, not silently replace."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / filename).write_bytes(payload)

    stats = mod_clean.clean_and_index(raw, tmp_path / "cold.db")

    assert stats["encoding_replaced_files"] == 1, f"{filename} was not flagged"


def test_cli_reports_marker_and_nonzero_exit(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bad.md").write_bytes(_illegal_bytes())
    monkeypatch.setattr(
        sys,
        "argv",
        ["01_clean_and_index.py", "--raw", str(raw), "--db", str(tmp_path / "cold.db")],
    )

    code = mod_clean.main()
    out = capsys.readouterr().out

    assert code == 2
    assert "ENCODING_REPLACED: file=1 chars=" in out
    assert "WARN:" in out and "bad.md" in out
    assert "INDEX_OK" not in out
    assert "Traceback" not in out


def test_valid_utf8_including_literal_replacement_char_is_not_flagged(tmp_path: pathlib.Path) -> None:
    """Valid UTF-8 (even containing a literal U+FFFD) takes the strict path and must not be flagged."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "ok.md").write_text(
        "## 2026-01-01\nUser: 合法文本含替换符 \ufffd 但整体仍是 UTF-8 内容",
        encoding="utf-8",
    )

    stats = mod_clean.clean_and_index(raw, tmp_path / "cold.db")

    assert stats["encoding_replaced_files"] == 0
    assert stats["encoding_replaced_chars"] == 0
