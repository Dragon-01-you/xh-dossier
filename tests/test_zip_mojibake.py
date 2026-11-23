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

import argparse
import json
import pathlib
import sys
import tarfile
import zipfile
from importlib import import_module

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

mod_doctor = import_module("00_doctor")
mod_io = import_module("archive_io")
mod_xh = import_module("xh")


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


# --- garbled-name detector unit cases --------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("00-总入口索引.md", False),
    ("AGENTS.md", False),
    ("00-总入口索引.md".encode("utf-8").decode("cp437"), True),
    ("02-鏍稿績鍒ゆ柇鍑嗗垯.md", True),
    ("00-\udcb5\udcc7+\udcd5.md", True),
    ("00-\ufffd.md", True),
    ("bad-锟斤拷.md", True),
])
def test_is_garbled_name(name: str, expected: bool) -> None:
    assert mod_io.is_garbled_name(name) is expected


# --- stdlib extraction round-trips -----------------------------------------


def _build_zip(path: pathlib.Path) -> None:
    names = [
        "templates/00-总入口索引.md",
        "templates/01-身份与当前主线.md",
        "templates/AGENTS.md",
        "scripts/00_doctor.py",
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, "# body\n")


def test_display_name_surrogates_become_replacement_char() -> None:
    raw = "00-\udcb5\udcc7+\udcd5.md"
    safe = mod_io.display_name(raw)
    json.dumps(safe)  # must not raise "surrogates not allowed"
    assert "\ufffd" in safe
    assert not any(0xD800 <= ord(ch) <= 0xDFFF for ch in safe)


def test_extract_zip_roundtrips_chinese_names(tmp_path: pathlib.Path) -> None:
    archive = tmp_path / "pkg.zip"
    _build_zip(archive)
    dest = tmp_path / "out"
    backend = mod_io.extract_archive(archive, dest)
    assert backend == "zipfile"
    names = sorted(p.name for p in (dest / "templates").iterdir())
    assert names == [
        "00-总入口索引.md",
        "01-身份与当前主线.md",
        "AGENTS.md",
    ]


def test_extract_tar_roundtrips_chinese_names(tmp_path: pathlib.Path) -> None:
    archive = tmp_path / "pkg.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for name in ["templates/00-总入口索引.md", "templates/AGENTS.md"]:
            data = b"# body\n"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, __import__("io").BytesIO(data))
    dest = tmp_path / "out"
    backend = mod_io.extract_archive(archive, dest)
    assert backend == "tarfile"
    names = sorted(p.name for p in (dest / "templates").iterdir())
    assert names == ["00-总入口索引.md", "AGENTS.md"]


# --- xh.py doctor classification -------------------------------------------


def _make_xh_root(tmp_path: pathlib.Path, garbled: bool) -> pathlib.Path:
    root = tmp_path / "xh_repo"
    (root / "scripts").mkdir(parents=True)
    (root / "templates").mkdir()
    (root / "examples" / "sample_raw").mkdir(parents=True)
    (root / "examples" / "sample_raw" / "demo.txt").write_text("ok\n", encoding="utf-8")
    for script in mod_xh.REQUIRED_SCRIPTS:
        (root / "scripts" / script).write_text("# placeholder\n", encoding="utf-8")
    for rel in [f"templates/{n}" for n in mod_xh.KIT_FILES]:
        base = pathlib.PurePosixPath(rel).name
        if base == "AGENTS.md":
            (root / rel).write_text("# ok\n", encoding="utf-8")
        elif garbled:
            bad = _cp437_mojibake(base)
            (root / "templates" / bad).write_text("# body\n", encoding="utf-8")
        else:
            (root / rel).write_text("# body\n", encoding="utf-8")
    return root


def test_xh_doctor_flags_encoding_corruption_not_missing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_xh_root(tmp_path, garbled=True)
    monkeypatch.setattr(mod_xh, "ROOT", root)
    monkeypatch.setattr(mod_xh, "TEMPLATES", root / "templates")
    monkeypatch.setattr(mod_xh, "SAMPLE_RAW", root / "examples" / "sample_raw")
    monkeypatch.setattr(mod_xh, "WORK", root / "work")

    code = mod_xh.doctor(argparse.Namespace())
    out = capsys.readouterr().out
    assert code == 1
    assert "ENCODING_CORRUPT" in out
    assert "missing template 00-总入口索引.md" not in out


def test_xh_doctor_reports_truly_missing_template(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_xh_root(tmp_path, garbled=False)
    (root / "templates" / "00-总入口索引.md").unlink()
    monkeypatch.setattr(mod_xh, "ROOT", root)
    monkeypatch.setattr(mod_xh, "TEMPLATES", root / "templates")
    monkeypatch.setattr(mod_xh, "SAMPLE_RAW", root / "examples" / "sample_raw")
    monkeypatch.setattr(mod_xh, "WORK", root / "work")

    code = mod_xh.doctor(argparse.Namespace())
    out = capsys.readouterr().out
    assert code == 1
    assert "missing template 00-总入口索引.md" in out
    assert "ENCODING_CORRUPT" not in out
