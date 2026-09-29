"""Alt+e 'GUI-like' edit shortcuts on the Configuration and Rates tabs.

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import asyncio

import pytest

import lexiflow.base as base_module
from lexiflow.tui import RateEditScreen, TranscriptorTUI


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


def test_alt_e_focuses_configuration_form(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.query_one("TabbedContent").active = "config"
            await pilot.pause()

            await pilot.press("alt+e")
            await pilot.pause()

            # editing happens in the tab itself: no modal, first field focused
            assert isolated_app.screen is isolated_app.screen_stack[0]
            assert isolated_app.screen.focused.id == "base_dir"

    asyncio.run(_run())


def test_alt_e_opens_rate_edit_screen(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()

            client_id = isolated_app.transcriptor.api.add_client(
                {"name": "Acme", "email": "acme@example.com"}
            )
            isolated_app.transcriptor.api.add_rates(
                {
                    "client_id": client_id,
                    "normal": 1.0,
                    "expedite": 2.0,
                    "interpreted": 3.0,
                }
            )

            isolated_app.query_one("TabbedContent").active = "rates"
            await pilot.pause()

            rates_pane = isolated_app.query_one("#rates-pane")
            rates_pane.refresh_table()
            rates_pane.get_table().focus()
            rates_pane.get_table().move_cursor(row=0)
            await pilot.pause()

            await pilot.press("alt+e")
            await pilot.pause()

            assert isinstance(isolated_app.screen, RateEditScreen)

    asyncio.run(_run())
