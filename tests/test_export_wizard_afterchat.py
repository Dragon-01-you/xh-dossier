# -*- coding: utf-8 -*-
"""Issues #4/#7: the wizard must surface the AfterChat worker, not just ScriptCat."""

from __future__ import annotations

import pathlib
import sys
from importlib import import_module

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

mod_wizard = import_module("00_export_wizard")


def test_wizard_prints_worker_url_and_activation_step(capsys) -> None:
    opened: list[str] = []
    result = mod_wizard.run_wizard(
        browser="edge",
        auto_yes=True,
        dry_run=True,
        open_url_fn=lambda url: opened.append(url) or True,
    )
    out = capsys.readouterr().out

    assert result["consented"] is True
    assert result["afterchat_url"] == mod_wizard.AFTERCHAT_URL
    assert opened == []
    assert "AfterChat" in out
    assert "589622" in out
    assert "白色圆形下载按钮" in out


def test_wizard_opens_both_engine_and_worker_pages_after_consent() -> None:
    opened: list[str] = []
    result = mod_wizard.run_wizard(
        browser="chrome",
        auto_yes=True,
        dry_run=False,
        open_url_fn=lambda url: opened.append(url) or True,
    )

    assert opened == [mod_wizard.EXTENSION_URLS["chrome"], mod_wizard.AFTERCHAT_URL]
    assert result["afterchat_opened"] is True


def test_wizard_can_disable_worker_page_opening() -> None:
    opened: list[str] = []
    result = mod_wizard.run_wizard(
        browser="edge",
        auto_yes=True,
        dry_run=False,
        open_afterchat=False,
        open_url_fn=lambda url: opened.append(url) or True,
    )

    assert opened == [mod_wizard.EXTENSION_URLS["edge"]]
    assert result["afterchat_opened"] is False
    assert result["afterchat_url"] == mod_wizard.AFTERCHAT_URL


def test_declined_wizard_still_returns_both_manual_links() -> None:
    opened: list[str] = []
    result = mod_wizard.run_wizard(
        browser="edge",
        auto_yes=False,
        input_fn=lambda _: "n",
        open_url_fn=lambda url: opened.append(url) or True,
    )

    assert result["consented"] is False
    assert opened == []
    assert result["afterchat_url"] == mod_wizard.AFTERCHAT_URL
