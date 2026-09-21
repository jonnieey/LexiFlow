"""DocumentProcessingScreen Select-population regression tests.

Uses Textual's Pilot to mount the real screen against a real job
directory containing actual files, verifying the notice/PBS/template
Selects populate from list_candidate_files() correctly and that
picking a notice excludes it from the PBS candidates.

Same isolation approach as test_tui_navigation.py -- see that file's
module docstring for why both HOME/XDG env vars and
lexiflow.base.DEFAULT_CONFIG['base_dir'] must be patched together.
"""

import asyncio

import pytest
from textual.widgets import Checkbox, Select

import lexiflow.base as base_module
from lexiflow.tui import DocumentProcessingScreen, TranscriptorTUI


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


def _job_dir_with_files(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "notice.pdf").touch()
    (job_dir / "pbs.pdf").touch()
    (job_dir / "template.docx").touch()
    (job_dir / "readme.txt").touch()  # should never appear in any Select
    audio = job_dir / "audio.mp3"
    audio.write_text("fake audio")
    return job_dir, audio


def test_selects_populate_from_job_directory(isolated_app, tmp_path):
    job_dir, audio = _job_dir_with_files(tmp_path)

    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(
                DocumentProcessingScreen(
                    {"id": 1, "job_number": "J1", "job_path": str(audio)}
                )
            )
            await pilot.pause()

            notice_select = isolated_app.screen.query_one(
                "#doc-notice", Select
            )
            pbs_select = isolated_app.screen.query_one("#doc-pbs", Select)
            template_select = isolated_app.screen.query_one(
                "#doc-template", Select
            )

            notice_values = {
                v for _, v in notice_select._options if v is not Select.BLANK
            }
            pbs_values = {
                v for _, v in pbs_select._options if v is not Select.BLANK
            }
            template_values = {
                v
                for _, v in template_select._options
                if v is not Select.BLANK
            }

            assert notice_values == {
                str(job_dir / "notice.pdf"),
                str(job_dir / "pbs.pdf"),
            }
            assert pbs_values == notice_values
            assert template_values == {str(job_dir / "template.docx")}

    asyncio.run(_run())


def test_picking_notice_excludes_it_from_pbs_options(isolated_app, tmp_path):
    job_dir, audio = _job_dir_with_files(tmp_path)

    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(
                DocumentProcessingScreen(
                    {"id": 1, "job_number": "J1", "job_path": str(audio)}
                )
            )
            await pilot.pause()

            notice_select = isolated_app.screen.query_one(
                "#doc-notice", Select
            )
            notice_select.value = str(job_dir / "notice.pdf")
            await pilot.pause()

            pbs_select = isolated_app.screen.query_one("#doc-pbs", Select)
            pbs_values = {
                v for _, v in pbs_select._options if v is not Select.BLANK
            }
            assert pbs_values == {str(job_dir / "pbs.pdf")}

    asyncio.run(_run())


def test_use_existing_metadata_checkbox_disabled_when_no_metadata_json(
    isolated_app, tmp_path
):
    job_dir, audio = _job_dir_with_files(tmp_path)

    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(
                DocumentProcessingScreen(
                    {"id": 1, "job_number": "J1", "job_path": str(audio)}
                )
            )
            await pilot.pause()

            checkbox = isolated_app.screen.query_one(
                "#doc-use-metadata", Checkbox
            )
            assert checkbox.disabled is True
            assert checkbox.value is False

    asyncio.run(_run())


def test_use_existing_metadata_checkbox_enabled_when_metadata_json_present(
    isolated_app, tmp_path
):
    job_dir, audio = _job_dir_with_files(tmp_path)
    (job_dir / "metadata.json").write_text("{}")

    async def _run():
        async with isolated_app.run_test() as pilot:
            await pilot.pause()
            isolated_app.push_screen(
                DocumentProcessingScreen(
                    {"id": 1, "job_number": "J1", "job_path": str(audio)}
                )
            )
            await pilot.pause()

            checkbox = isolated_app.screen.query_one(
                "#doc-use-metadata", Checkbox
            )
            assert checkbox.disabled is False
            assert checkbox.value is True

    asyncio.run(_run())
