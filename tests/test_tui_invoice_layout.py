"""Invoicing tab fits small terminals: controls compact, results and
cutoffs visible without scrolling, every button on screen.

Isolation as in test_tui_navigation.py (HOME/XDG + DEFAULT_CONFIG base_dir).
"""

import asyncio

import pytest
from textual.widgets import Label

import lexiflow.base as base_module
from lexiflow.tui import Invoice, TranscriptorTUI


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )
    return TranscriptorTUI()


async def _open_invoicing(app, pilot) -> Invoice:
    app.query_one("TabbedContent").active = "invoicing"
    await pilot.pause()
    return app.query_one(Invoice)


@pytest.mark.parametrize("size", [(80, 24), (120, 30)])
def test_jobs_table_visible_without_scrolling(isolated_app, size):
    async def _run():
        async with isolated_app.run_test(size=size) as pilot:
            await pilot.pause()
            tab = await _open_invoicing(isolated_app, pilot)
            screen = isolated_app.screen

            layout = tab.query_one("#invoice-main-layout")
            assert not [c for c in layout.children if isinstance(c, Label)]

            pane = tab.query_one("#invoice-input-pane")
            assert getattr(pane, "max_scroll_y", 0) == 0
            table = tab.query_one("#invoice-jobs-table").region
            assert screen.region.contains_region(table)
            assert table.height >= 5
            for wid in ("#client-select", "#start-date", "#end-date"):
                widget = tab.query_one(wid)
                assert "field-row" in widget.parent.classes, wid

    asyncio.run(_run())


def test_date_inputs_fit_a_full_date_at_80_cols(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            tab = await _open_invoicing(isolated_app, pilot)
            for wid in ("#start-date", "#end-date"):
                # "2026-03-01" plus the input's own padding
                assert tab.query_one(wid).region.width >= 12, wid

    asyncio.run(_run())
