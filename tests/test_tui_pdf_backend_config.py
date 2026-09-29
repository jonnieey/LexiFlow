"""TUI configuration screen: pdf_backend select.

Isolation as in test_tui_navigation.py (HOME/XDG + DEFAULT_CONFIG base_dir).
"""

import asyncio

import pytest
from textual.widgets import Select, Static

import lexiflow.base as base_module
from lexiflow.models import Config
from lexiflow.pdf import PDFRenderer
from lexiflow.tui import ConfigurationScreen, TranscriptorTUI


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setitem(
        base_module.DEFAULT_CONFIG, "base_dir", str(tmp_path / "data")
    )
    monkeypatch.setattr(PDFRenderer, "_default_backend", None)
    monkeypatch.setattr(PDFRenderer, "_backends", {"xhtml2pdf": object})
    return TranscriptorTUI()


def test_config_screen_saves_and_applies_pdf_backend(isolated_app):
    backend = "xhtml2pdf"

    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(ConfigurationScreen())
            await pilot.pause()

            select = isolated_app.screen.query_one("#pdf_backend", Select)
            assert select.value == "auto"
            select.value = backend
            await pilot.pause()

            isolated_app.screen.save_config()
            await pilot.pause()

    asyncio.run(_run())

    t = isolated_app.transcriptor
    assert t.config.pdf_backend == backend
    assert Config.from_yaml(t.CONFIG_FILE).pdf_backend == backend
    assert PDFRenderer.get_default_backend() == backend


def test_config_display_shows_pdf_backend(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.query_one("TabbedContent").active = "config"
            await pilot.pause()
            text = str(
                isolated_app.query_one("#config-display", Static).render()
            )
            assert "PDF Backend: auto" in text

    asyncio.run(_run())


def test_config_screen_lists_uninstalled_backends(isolated_app):
    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(ConfigurationScreen())
            await pilot.pause()
            select = isolated_app.screen.query_one("#pdf_backend", Select)
            labels = {str(label): value for label, value in select._options}
            assert labels["weasyprint (not installed)"] == "weasyprint"
            assert labels["xhtml2pdf"] == "xhtml2pdf"

    asyncio.run(_run())


def test_config_screen_saves_uninstalled_backend_without_applying(isolated_app):
    notes = []

    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.notify = lambda msg, **k: notes.append(msg)
            isolated_app.push_screen(ConfigurationScreen())
            await pilot.pause()
            isolated_app.screen.query_one("#pdf_backend", Select).value = (
                "weasyprint"
            )
            await pilot.pause()
            isolated_app.screen.save_config()
            await pilot.pause()

    asyncio.run(_run())

    assert isolated_app.transcriptor.config.pdf_backend == "weasyprint"
    assert PDFRenderer.get_default_backend() is None
    assert any("not installed" in n for n in notes)
