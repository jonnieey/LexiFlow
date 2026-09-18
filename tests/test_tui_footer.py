"""Footer widget regression test.

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import pytest
from textual.widgets import Footer

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


def test_app_uses_real_textual_footer_widget(isolated_app):
    """The app must mount Textual's own Footer, not a hand-rolled one."""
    import asyncio

    async def _run():
        async with isolated_app.run_test():
            footers = isolated_app.query(Footer)
            assert len(footers) == 1
            assert type(footers.first()) is Footer

    asyncio.run(_run())
