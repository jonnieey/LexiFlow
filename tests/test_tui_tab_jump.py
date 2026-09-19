"""Number-key tab jump regression test.

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import asyncio

import pytest

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


def test_number_keys_jump_directly_to_matching_tab(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            tabs = isolated_app.query_one("TabbedContent")
            assert tabs.active == "dashboard"

            await pilot.press("3")
            await pilot.pause()
            assert tabs.active == "clients"

            await pilot.press("7")
            await pilot.pause()
            assert tabs.active == "config"

            await pilot.press("1")
            await pilot.pause()
            assert tabs.active == "dashboard"

    asyncio.run(_run())
