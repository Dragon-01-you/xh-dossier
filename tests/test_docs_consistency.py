# -*- coding: utf-8 -*-
"""Issue #17: Stage 1 docs must agree on the 6-round interview contract."""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_readme_stage1_round_count_matches_interview_skill() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "onboarding-interviewer" / "SKILL.md").read_text(encoding="utf-8")

    assert "6 轮" in readme
    assert "4~5 轮" not in readme
    assert "4-5 轮" not in readme
    assert "每次 3 个选择题" not in readme

    assert "6 轮" in skill
    assert "每轮只问 `3` 个问题" in skill


def test_readme_declares_dev_dependencies_for_pytest() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    requirements = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "Python 3.10+" in readme
    assert "requirements-dev.txt" in readme
    assert "python -m pip install -r requirements-dev.txt" in readme
    assert "pytest" in requirements.lower()
