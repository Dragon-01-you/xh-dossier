# -*- coding: utf-8 -*-
"""Tests for the new doctor / smoke Stage 0 entry points."""

from __future__ import annotations

import pathlib
import subprocess
import sys
from importlib import import_module

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

mod_doctor = import_module("00_doctor")
mod_smoke = import_module("99_smoke")


def run_cli(script: str, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS_DIR / script), *map(str, args)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_doctor_ok_on_clean_repo() -> None:
    proc = run_cli("00_doctor.py")
    combined = f"{proc.stdout or ''}{proc.stderr or ''}"
    assert proc.returncode == 0, combined
    assert "DOCTOR_OK" in combined
    assert "FTS5 + trigram" in combined
    assert "Traceback" not in combined


def test_doctor_bad_root_is_human_error_not_traceback() -> None:
    proc = run_cli("00_doctor.py", "--root", str(REPO_ROOT / "definitely_missing_dir"))
    combined = f"{proc.stdout or ''}{proc.stderr or ''}"
    assert proc.returncode == 2, combined
    assert "DOCTOR_FAIL" in combined
    assert "仓库根目录不存在" in combined
    assert "Traceback" not in combined


def test_doctor_rejects_low_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 10))
    with pytest.raises(mod_doctor.DoctorError) as exc:
        mod_doctor.check_python()
    assert "Python 版本过低" in str(exc.value)
    assert "3.11" in str(exc.value)


def test_doctor_detects_missing_script(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = tmp_path / "fake_repo"
    (fake / "templates").mkdir(parents=True)
    with pytest.raises(mod_doctor.DoctorError) as exc:
        mod_doctor.check_files(fake)
    assert "缺少必需文件" in str(exc.value)


def test_smoke_ok() -> None:
    proc = run_cli("99_smoke.py")
    combined = f"{proc.stdout or ''}{proc.stderr or ''}"
    assert proc.returncode == 0, combined
    assert "SMOKE_OK" in combined
    assert "INDEX_OK" in combined
    assert "FOUR_WAY_OK" in combined
    assert "VALIDATE_OK" in combined
    assert "Traceback" not in combined
