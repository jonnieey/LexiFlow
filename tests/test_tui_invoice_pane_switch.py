"""Ctrl+w pane-switch regression test for the split-pane Invoice screen.

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import asyncio

import pytest
from textual.widgets import DataTable

import lexiflow.base as base_module
from lexiflow.tui import TranscriptorTUI


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )

    app = TranscriptorTUI()
    assert str(app.transcriptor.base_dir) == str(tmp_path / "data")
    return app


def test_ctrl_w_toggles_focus_between_invoice_panes(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.query_one("TabbedContent").active = "invoicing"
            await pilot.pause()

            left = isolated_app.query_one("#invoice-jobs-table", DataTable)
            right = isolated_app.query_one(
                "#invoice-cutoffs-table", DataTable
            )
            right.focus()
            await pilot.pause()
            assert isolated_app.screen.focused is right

            await pilot.press("ctrl+w")
            await pilot.pause()
            assert isolated_app.screen.focused is left

            await pilot.press("ctrl+w")
            await pilot.pause()
            assert isolated_app.screen.focused is right

    asyncio.run(_run())
