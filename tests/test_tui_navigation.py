"""Navigation/keymap regression tests for the TUI shell.

Uses Textual's Pilot to drive a real, isolated app instance -- HOME/XDG
env vars AND lexiflow.base.DEFAULT_CONFIG['base_dir'] are redirected to
tmp_path so this never touches the user's real ~/.config or
~/.local/share data. Both are needed: DEFAULT_CONFIG['base_dir'] is a
module-level dict computed once at import time from the *real* HOME
(platformdirs.user_data_dir), so patching HOME alone is not enough --
any Transcriptor() built after that import still defaults its base_dir
to the real data directory.
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
    for i in range(2):
        app.transcriptor.api.add_job(
            {
                "client_id": client_id,
                "date_received": "2026-01-01",
                "job_number": f"J{i}",
                "job_type": "normal",
                "status": "Pending",
                "date_due": "2026-01-10",
                "total_quantity": 1.0,
                "quantity": 1.0,
                "job_rate": 1.0,
                "amount": 1.0,
                "job_path": str(tmp_path / f"job{i}"),
            }
        )
    return app


def test_vim_movement_works_without_toggling_vim_mode(isolated_app):
    """j/k must move the table cursor immediately -- no 'v' toggle required."""

    async def _run():
        async with isolated_app.run_test() as pilot:
            table = isolated_app.query_one("#pending-jobs-table")
            assert table.cursor_row == 0
            await pilot.press("j")
            assert table.cursor_row == 1

    asyncio.run(_run())


def test_app_has_no_vim_mode_toggle(isolated_app):
    """The 'v' toggle binding/reactive/action must be gone -- vim keys are
    always on, so there is nothing left to toggle."""
    assert not hasattr(isolated_app, "vim_mode")
    assert not hasattr(isolated_app, "action_toggle_vim_mode")
    binding_keys = {b[0] for b in isolated_app.BINDINGS}
    assert "v" not in binding_keys
