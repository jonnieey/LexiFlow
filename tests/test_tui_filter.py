"""'/' filter regression tests for vim-navigable table panes.

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

    client_id = app.transcriptor.api.add_client(
        {"name": "Acme", "email": "acme@example.com"}
    )
    for job_number in ("ALPHA-1", "BRAVO-2"):
        app.transcriptor.api.add_job(
            {
                "client_id": client_id,
                "date_received": "2026-01-01",
                "job_number": job_number,
                "job_type": "normal",
                "status": "Pending",
                "date_due": "2026-01-10",
                "total_quantity": 1.0,
                "quantity": 1.0,
                "job_rate": 1.0,
                "amount": 1.0,
                "job_path": str(tmp_path / job_number),
            }
        )
    return app


def test_slash_filters_table_rows_live(isolated_app):
    """'/' opens a filter; typing narrows visible rows to matches."""

    async def _run():
        async with isolated_app.run_test() as pilot:
            # Let the dashboard tab's deferred activation-focus settle
            # first -- pressing '/' in the same tick would otherwise race
            # against it and lose focus back to the table.
            await pilot.pause()
            table = isolated_app.query_one("#pending-jobs-table")
            assert table.row_count == 2

            await pilot.press("/")
            await pilot.press("a", "l", "p", "h", "a")
            assert table.row_count == 1

    asyncio.run(_run())


def test_escape_clears_filter_and_restores_all_rows(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            table = isolated_app.query_one("#pending-jobs-table")
            await pilot.press("/")
            await pilot.press("a", "l", "p", "h", "a")
            assert table.row_count == 1

            await pilot.press("escape")
            assert table.row_count == 2

    asyncio.run(_run())


def test_typing_in_filter_does_not_trigger_vim_keys(isolated_app):
    """While the filter input has focus, 'j' must be typed, not move the cursor."""

    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            table = isolated_app.query_one("#pending-jobs-table")
            assert table.cursor_row == 0

            await pilot.press("/")
            await pilot.press("j")  # should type "j", not move the cursor
            assert table.cursor_row == 0

    asyncio.run(_run())
