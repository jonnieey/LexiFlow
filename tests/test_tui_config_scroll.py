"""Edit Configuration modal must scroll so every field is reachable.

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


def test_config_form_scrolls_to_last_field(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.push_screen(ConfigurationScreen())
            await pilot.pause()
            screen = isolated_app.screen

            form = screen.query_one("#config-form", VerticalScroll)
            assert form.max_scroll_y > 0  # content taller than the modal

            last = screen.query_one("#pdf_backend", Select)
            last.focus()
            await pilot.pause()
            await pilot.pause()

            assert form.scroll_y > 0
            assert form.region.contains_region(last.region)
            # Save/Cancel stay visible, docked below the form
            save = screen.query_one("#save-config")
            assert screen.region.contains_region(save.region)

    asyncio.run(_run())
