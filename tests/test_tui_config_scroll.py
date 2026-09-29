"""Edit Configuration modal must show every field on a small terminal.

Isolation as in test_tui_navigation.py (HOME/XDG + DEFAULT_CONFIG base_dir).
"""

import asyncio

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Select

import lexiflow.base as base_module
from lexiflow.tui import ConfigurationScreen, TranscriptorTUI


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )
    return TranscriptorTUI()


def test_config_form_fits_without_scrolling(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.push_screen(ConfigurationScreen())
            await pilot.pause()
            screen = isolated_app.screen

            form = screen.query_one("#config-form", VerticalScroll)
            assert form.max_scroll_y == 0

            last = screen.query_one("#pdf_backend", Select)
            assert form.region.contains_region(last.region)
            # Save/Cancel stay visible, docked below the form
            save = screen.query_one("#save-config")
            assert screen.region.contains_region(save.region)

    asyncio.run(_run())
