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
    AddJobScreen,
    AddCutoffsScreen,
    ClientEditScreen,
    DocumentProcessingScreen,
    JobEditScreen,
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


@pytest.mark.parametrize(
    "make_screen",
    SIMPLE_FORMS,
    ids=["client-edit", "client-add", "rate-edit", "profile-edit", "cutoffs"],
)
def test_simple_forms_shrink_to_content_and_center(isolated_app, make_screen):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.push_screen(make_screen())
            await pilot.pause()
            screen = isolated_app.screen
            box = screen.query_one(f"#{make_screen().get_container_id()}")
            last_input = list(screen.query(Input))[-1]
            save = screen.query_one("#save")
            # no dead space between the last field and the buttons
            assert save.region.y - last_input.region.bottom <= 2
            # centered on screen
            left = box.region.x
            right = screen.region.right - box.region.right
            assert abs(left - right) <= 1

    asyncio.run(_run())


def _add_job_step(screen, step, tmp_path, monkeypatch):
    if step == 1:
        screen.load_step_1()
    elif step == 2:
        screen.job_data = {"job_file": str(tmp_path / "123_0915.zip")}
        screen.load_step_2()
    else:
        media = tmp_path / "audio.mp3"
        media.write_bytes(b"")
        monkeypatch.setattr(tui_module, "get_media_duration", lambda _: 1.5)
        screen.media_files = [media]
        screen.current_media_index = 0
        screen.load_current_media_form()


@pytest.mark.parametrize("step", [1, 2, 3])
def test_add_job_steps_use_compact_rows(
    isolated_app, tmp_path, monkeypatch, step
):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = AddJobScreen()
            isolated_app.push_screen(screen)
            await pilot.pause()
            _add_job_step(screen, step, tmp_path, monkeypatch)
            await pilot.pause()
            form = screen.query_one("#add-job-form")
            fields = list(form.query("Input, Select, Checkbox"))
            assert fields
            for widget in fields:
                if isinstance(widget, (Input, Select)):
                    assert "field-row" in widget.parent.classes, widget.id
            assert form.max_scroll_y == 0

    asyncio.run(_run())


JOB = {
    "job_number": "123",
    "client_id": "",
    "status": "Pending",
    "amount_paid": "",
    "job_type": "normal",
    "date_submitted": "",
    "job_rate": "1.0",
    "date_received": "2026-09-01",
    "date_due": "2026-09-05",
    "quantity": "10",
    "total_quantity": "10",
    "amount": "10",
    "job_path": "/jobs/123/a.mp3",
    "note": "",
}


def test_job_edit_fits_in_two_columns(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.push_screen(JobEditScreen(dict(JOB)))
            await pilot.pause()
            screen = isolated_app.screen
            form = screen.query_one("#job-form-container")
            for widget in screen.query("Input, Select"):
                assert "field-row" in widget.parent.classes, widget.id
            assert form.max_scroll_y == 0
            for left, right in [
                ("#date_received", "#date_due"),
                ("#quantity", "#total_quantity"),
                ("#status", "#job_type"),
            ]:
                a = screen.query_one(left).region
                b = screen.query_one(right).region
                assert a.y == b.y and a.right <= b.x
            save = screen.query_one("#save")
            assert screen.region.contains_region(save.region)

    asyncio.run(_run())


def test_job_edit_grid_still_collects_every_field(isolated_app):
    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = JobEditScreen(dict(JOB, client_id=7, amount_paid=0.0))
            isolated_app.push_screen(screen)
            await pilot.pause()
            values = screen.collect_values()
            assert values["job_number"] == "123"
            assert values["client_id"] == 7
            assert values["amount_paid"] == 0.0
            assert values["date_due"] == "2026-09-05"
            assert values["job_path"] == "/jobs/123/a.mp3"
            assert values["status"] == "Pending"
            assert values["job_type"] == "normal"
            assert values["total_quantity"] == 10.0

    asyncio.run(_run())


def test_document_processing_fits_small_terminal(isolated_app, tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    for name in ("notice.pdf", "pbs.pdf", "template.docx"):
        (job_dir / name).touch()
    audio = job_dir / "audio.mp3"
    audio.write_text("fake audio")
    job = {
        "id": 1,
        "job_number": "J1",
        "job_path": str(audio),
        # worst case: every info line shown
        "provider": "speechmatics",
        "external_job_id": "abc",
        "transcription_status": "running",
        "transcription_last_polled_at": "2026-09-29 10:00",
        "transcription_last_error": "timeout",
    }

    async def _run():
        async with isolated_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            isolated_app.push_screen(DocumentProcessingScreen(job))
            await pilot.pause()
            screen = isolated_app.screen
            for select in screen.query(Select):
                assert "field-row" in select.parent.classes, select.id
            notice = screen.query_one("#doc-notice").region
            pbs = screen.query_one("#doc-pbs").region
            assert notice.y == pbs.y
            for button in screen.query("Button"):
                assert screen.region.contains_region(button.region), button.id

    asyncio.run(_run())
