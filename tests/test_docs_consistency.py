# -*- coding: utf-8 -*-
"""Issue #17: Stage 1 docs must agree on the 6-stage interview contract."""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_readme_stage1_stage_count_matches_interview_skill() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "skills" / "onboarding-interviewer" / "SKILL.md").read_text(encoding="utf-8")

    assert "6 个阶段" in readme
    assert "4~5 阶段" not in readme
    assert "4-5 阶段" not in readme
    assert "每次 3 个选择题" not in readme

    assert "6 个阶段" in skill
    assert "每阶段先问 2–3 个种子问题" in skill
    assert "不把 3 题当上限" in skill


def test_readme_declares_dev_dependencies_for_pytest() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    requirements = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "Python 3.11+" in readme
    assert "requirements-dev.txt" in readme
    assert "python -m pip install -r requirements-dev.txt" in readme
    assert "pytest" in requirements.lower()
