"""Small dialogs (delete confirmation, About) are compact, centered boxes.

Isolation as in test_tui_navigation.py (HOME/XDG + DEFAULT_CONFIG base_dir).
"""

import asyncio

import pytest
from textual.widgets import Button, Label

import lexiflow.base as base_module
from lexiflow.tui import ConfirmDelete, TranscriptorTUI


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )
    return TranscriptorTUI()


def _assert_centered_box(screen, box):
    assert box.region.width < screen.region.width
    assert box.region.height < screen.region.height // 2
    left = box.region.x
    right = screen.region.right - box.region.right
    assert abs(left - right) <= 1


def test_confirm_delete_is_a_small_centered_box(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.push_screen(ConfirmDelete("job"))
            await pilot.pause()
            screen = isolated_app.screen
            box = screen.query_one("#confirm-delete-box")
            _assert_centered_box(screen, box)
            message = box.query_one(".confirm-title", Label)
            yes = box.query_one("#confirm-delete-yes", Button)
            # message above the buttons, not squeezed beside them
            assert message.region.bottom <= yes.region.y
            # red is reserved for the destructive action
            assert yes.variant == "error"

    asyncio.run(_run())

