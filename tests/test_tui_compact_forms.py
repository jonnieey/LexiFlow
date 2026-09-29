"""Compact form rows: label + widget share one terminal row, so modal
forms fit small terminals without scrolling.
"""

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input, Label, Select

import lexiflow.tui as tui_module
from lexiflow.tui import field_row


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
