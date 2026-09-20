"""Vim-centric modal navigation regression tests: j/k move focus,
Escape cancels/closes -- matching each screen's existing Cancel/Close
button behavior exactly (some dismiss with True, some False, some
None; these values are relied on by callers via push_screen callbacks,
so Escape must reproduce them, not just "dismiss").

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import asyncio

import pytest
from textual.widgets import Button, ListView

import lexiflow.base as base_module
from lexiflow.tui import AddClientScreen, ConfirmDelete, JobContextMenu


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )

    from lexiflow.tui import TranscriptorTUI

    app = TranscriptorTUI()
    assert str(app.transcriptor.base_dir) == str(tmp_path / "data")
    return app


def test_confirm_delete_jk_moves_between_buttons_and_escape_cancels(
    isolated_app,
):
    async def _run():
        result = {}

        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(
                ConfirmDelete("job"), lambda r: result.setdefault("value", r)
            )
            await pilot.pause()

            yes = isolated_app.screen.query_one("#confirm-delete-yes", Button)
            no = isolated_app.screen.query_one("#confirm-delete-no", Button)
            yes.focus()
            await pilot.pause()
            assert isolated_app.screen.focused is yes

            await pilot.press("j")
            await pilot.pause()
            assert isolated_app.screen.focused is no

            await pilot.press("k")
            await pilot.pause()
            assert isolated_app.screen.focused is yes

            await pilot.press("escape")
            await pilot.pause()
            assert result["value"] is False

    asyncio.run(_run())


def test_job_context_menu_jk_moves_listview_highlight_and_escape_closes(
    isolated_app,
):
    async def _run():
        closed = {"value": "not-called"}

        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(
                JobContextMenu({"id": 1, "job_number": "J1"}),
                lambda r: closed.__setitem__("value", r),
            )
            await pilot.pause()

            list_view = isolated_app.screen.query_one("#action-list", ListView)
            assert list_view.index == 0

            await pilot.press("j")
            await pilot.pause()
            assert list_view.index == 1

            await pilot.press("k")
            await pilot.pause()
            assert list_view.index == 0

            await pilot.press("escape")
            await pilot.pause()
            assert closed["value"] is None

    asyncio.run(_run())


def test_add_client_screen_escape_cancels(isolated_app):
    async def _run():
        result = {"value": "not-called"}

        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(
                AddClientScreen(), lambda r: result.__setitem__("value", r)
            )
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            assert result["value"] is False

    asyncio.run(_run())
