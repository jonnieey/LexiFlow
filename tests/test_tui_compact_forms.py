"""Compact form rows: label + widget share one terminal row, so modal
forms fit small terminals without scrolling.
"""

import asyncio
from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Label, Select

import lexiflow.base as base_module
import lexiflow.tui as tui_module
from lexiflow.tui import (
    AddClientScreen,
    AddCutoffsScreen,
    ClientEditScreen,
    ProfileEditScreen,
    RateEditScreen,
    TranscriptorTUI,
    field_row,
)


class _RowApp(App):
    # the real app stylesheet, so compact-row rules are exercised
    CSS_PATH = str(Path(tui_module.__file__).parent / "tui.css")

    def compose(self) -> ComposeResult:
        yield field_row("Name:", Input(value="x", id="name"))
        yield field_row("Kind:", Select([("a", "a")], value="a", id="kind"))


def test_field_row_puts_label_and_widget_on_one_row():
    async def _run():
        app = _RowApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for wid in ("#name", "#kind"):
                widget = app.query_one(wid)
                row = widget.parent
                assert "field-row" in row.classes
                assert row.region.height == 1
                label = row.query_one(Label)
                assert label.region.y == widget.region.y

    asyncio.run(_run())


def test_compact_select_still_opens_overlay():
    async def _run():
        app = _RowApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            select = app.query_one("#kind", Select)
            select.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert select.expanded

    asyncio.run(_run())


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )
    return TranscriptorTUI()


SIMPLE_FORMS = [
    lambda: ClientEditScreen({"name": "Acme", "email": "a@b.c"}),
    lambda: AddClientScreen(),
    lambda: RateEditScreen(
        {"client_name": "Acme", "normal": 1, "expedite": 2, "interpreted": 3}
    ),
    lambda: ProfileEditScreen({"name": "Me", "area": "X", "country": "KE"}),
    lambda: AddCutoffsScreen(),
]


@pytest.mark.parametrize(
    "make_screen",
    SIMPLE_FORMS,
    ids=["client-edit", "client-add", "rate-edit", "profile-edit", "cutoffs"],
)
def test_simple_forms_use_compact_rows(isolated_app, make_screen):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.push_screen(make_screen())
            await pilot.pause()
            screen = isolated_app.screen
            inputs = list(screen.query(Input))
            assert inputs
            for widget in inputs:
                assert "field-row" in widget.parent.classes, widget.id
                assert screen.region.contains_region(widget.region)

    asyncio.run(_run())
