""":' command palette regression test.

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import asyncio

import pytest
from textual.command import CommandPalette

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


def test_colon_opens_command_palette(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            await pilot.press(":")
            await pilot.pause()
            assert isinstance(isolated_app.screen, CommandPalette)

    asyncio.run(_run())
