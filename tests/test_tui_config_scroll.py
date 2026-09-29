"""Configuration is edited directly in its tab: every field, Save/Revert
and the Data Management buttons fit a small terminal without scrolling.

Isolation as in test_tui_navigation.py (HOME/XDG + DEFAULT_CONFIG base_dir).
"""

import asyncio

import pytest
from textual.widgets import Input

import lexiflow.base as base_module
from lexiflow.tui import Configuration, TranscriptorTUI


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )
    return TranscriptorTUI()


def test_config_tab_form_fits_without_scrolling(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.query_one("TabbedContent").active = "config"
            await pilot.pause()
            tab = isolated_app.query_one(Configuration)
            container = tab.query_one("#config-container")
            assert container.max_scroll_y == 0
            screen = isolated_app.screen
            for wid in (
                "#base_dir",
                "#pdf_backend",
                "#save-config",
                "#revert-config",
                "#backup-db",
            ):
                region = tab.query_one(wid).region
                assert screen.region.contains_region(region), wid

    asyncio.run(_run())


def test_config_tab_saves_and_reverts(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.query_one("TabbedContent").active = "config"
            await pilot.pause()
            tab = isolated_app.query_one(Configuration)
            date_format = tab.query_one("#date_format", Input)
            date_format.value = "%d/%m/%Y"
            tab.save_config()
            await pilot.pause()
            assert isolated_app.transcriptor.config.date_format == "%d/%m/%Y"

            # unsaved edit is discarded by Revert
            date_format.value = "junk"
            await pilot.click("#revert-config")
            await pilot.pause()
            assert date_format.value == "%d/%m/%Y"
            assert isolated_app.transcriptor.config.date_format == "%d/%m/%Y"

    asyncio.run(_run())
