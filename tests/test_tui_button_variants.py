"""Button variant regression tests for the CSS/visual polish pass.

Every button-bar button previously rendered solid orange regardless of
what it did (Add/Edit/Delete/Refresh all looked identical). This
checks a representative sample now carries a real semantic variant
(primary/error/success) instead of the CSS-forced blanket color.

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import pytest
from textual.widgets import Button

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


def test_dashboard_add_job_is_primary(isolated_app):
    import asyncio

    async def _run():
        async with isolated_app.run_test():
            button = isolated_app.query_one("#dash-add-job", Button)
            assert button.variant == "primary"

    asyncio.run(_run())


def test_clients_delete_is_error_variant(isolated_app):
    import asyncio

    async def _run():
        async with isolated_app.run_test() as pilot:
            isolated_app.query_one("TabbedContent").active = "clients"
            await pilot.pause()
            button = isolated_app.query_one("#clients-delete", Button)
            assert button.variant == "error"

    asyncio.run(_run())


def test_dashboard_edit_and_refresh_stay_default(isolated_app):
    """Not every button needs a loud variant -- secondary actions stay default."""
    import asyncio

    async def _run():
        async with isolated_app.run_test():
            edit = isolated_app.query_one("#dash-edit-job", Button)
            refresh = isolated_app.query_one("#dash-refresh", Button)
            assert edit.variant == "default"
            assert refresh.variant == "default"

    asyncio.run(_run())
