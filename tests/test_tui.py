import asyncio
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from textual.widgets import Select

from lexiflow.tui import (
    AddJobScreen,
    Dashboard,
    DocumentProcessingScreen,
    JobContextMenu,
    JobsTable,
)


def _screen_with_mock_app(screen=None):
    screen = screen if screen is not None else AddJobScreen()
    patcher = patch.object(type(screen), "app", new_callable=PropertyMock)
    mock_app_prop = patcher.start()
    mock_app_prop.return_value = MagicMock()
    return screen, patcher


def test_mv_extract_job_file_rejects_path_traversal(tmp_path):
    """Zip members that escape the target directory must not be extracted."""
    zip_path = tmp_path / "malicious.zip"
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.txt", "pwned")

    screen, patcher = _screen_with_mock_app()
    try:
        screen.mv_extract_job_file(zip_path, job_dir)
        assert not (tmp_path / "evil.txt").exists()
        notify_call = screen.app.notify.call_args
        assert "escapes target directory" in notify_call.args[0]
    finally:
        patcher.stop()


def test_mv_extract_job_file_extracts_benign_zip(tmp_path):
    zip_path = tmp_path / "job.zip"
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("audio.mp3", "fake audio content")

    screen, patcher = _screen_with_mock_app()
    try:
        screen.mv_extract_job_file(zip_path, job_dir)
        assert (job_dir / "audio.mp3").exists()
        assert not zip_path.exists()
    finally:
        patcher.stop()


def test_mv_extract_job_file_ignores_bare_root_zip_entry(tmp_path):
    """A zip member literally named '/' (a harmless top-level directory
    entry some zip tools include) must not be flagged as a path-traversal
    escape -- see the matching fix/test in lexiflow.base."""
    zip_path = tmp_path / "job_with_root_entry.zip"
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("/", "")
        zf.writestr("audio.mp3", "fake audio content")

    screen, patcher = _screen_with_mock_app()
    try:
        screen.mv_extract_job_file(zip_path, job_dir)
        assert (job_dir / "audio.mp3").exists()
        screen.app.notify.assert_not_called()
    finally:
        patcher.stop()


def test_mv_extract_job_file_copies_non_zip(tmp_path):
    src_file = tmp_path / "audio.mp3"
    src_file.write_text("fake audio content")
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()

    screen, patcher = _screen_with_mock_app()
    try:
        screen.mv_extract_job_file(src_file, job_dir)
        assert (job_dir / "audio.mp3").exists()
        assert src_file.exists()  # copy, not move
    finally:
        patcher.stop()


# -------- DocumentProcessingScreen --------


def _document_processing_screen_with_mock_app(job_data):
    screen, patcher = _screen_with_mock_app(DocumentProcessingScreen(job_data))
    screen.app.transcriptor = AsyncMock()
    return screen, patcher


def test_doc_do_extract_saves_metadata_json(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {
                "WITNESS_NAME": "Jane Doe"
            }
            metadata = asyncio.run(screen.do_extract(notice, pbs))

        assert metadata == {"WITNESS_NAME": "Jane Doe"}
        mock_extractor_cls.return_value.extract_all.assert_called_once_with(
            notice, pbs
        )
        metadata_path = tmp_path / "metadata.json"
        assert metadata_path.exists()
        assert json.loads(metadata_path.read_text()) == {
            "WITNESS_NAME": "Jane Doe"
        }
    finally:
        patcher.stop()


def test_doc_do_extract_notice_only(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        notice = tmp_path / "notice.pdf"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {
                "A": "1"
            }
            metadata = asyncio.run(screen.do_extract(notice, None))

        assert metadata == {"A": "1"}
        mock_extractor_cls.return_value.extract_all.assert_called_once_with(
            notice, None
        )
    finally:
        patcher.stop()


def test_doc_do_extract_pbs_only(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        pbs = tmp_path / "pbs.pdf"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {
                "A": "1"
            }
            metadata = asyncio.run(screen.do_extract(None, pbs))

        assert metadata == {"A": "1"}
        mock_extractor_cls.return_value.extract_all.assert_called_once_with(
            None, pbs
        )
    finally:
        patcher.stop()


def test_doc_do_fill_reuses_existing_metadata_json_by_default(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    (tmp_path / "metadata.json").write_text(json.dumps({"A": "1"}))
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        template = tmp_path / "template.docx"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            with patch("lexiflow.tui.fill_template") as mock_fill:
                mock_fill.return_value = tmp_path / "template_filled.docx"
                result = asyncio.run(
                    screen.do_fill(None, None, template, use_existing=True)
                )

        mock_extractor_cls.assert_not_called()
        mock_fill.assert_called_once_with(template, {"A": "1"}, None)
        assert result == tmp_path / "template_filled.docx"
    finally:
        patcher.stop()


def test_doc_do_fill_extracts_when_use_existing_false(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    (tmp_path / "metadata.json").write_text(json.dumps({"A": "1"}))
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        template = tmp_path / "template.docx"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {
                "B": "2"
            }
            with patch("lexiflow.tui.fill_template") as mock_fill:
                asyncio.run(
                    screen.do_fill(
                        notice, pbs, template, use_existing=False
                    )
                )

        mock_extractor_cls.return_value.extract_all.assert_called_once_with(
            notice, pbs
        )
        mock_fill.assert_called_once_with(template, {"B": "2"}, None)
    finally:
        patcher.stop()


def test_doc_do_fill_raises_without_metadata_or_notice_pbs(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        template = tmp_path / "template.docx"
        with pytest.raises(ValueError, match="Select a notice and/or"):
            asyncio.run(screen.do_fill(None, None, template))
    finally:
        patcher.stop()


def test_doc_do_fill_notice_only_extracts(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        notice = tmp_path / "notice.pdf"
        template = tmp_path / "template.docx"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {
                "A": "1"
            }
            with patch("lexiflow.tui.fill_template") as mock_fill:
                mock_fill.return_value = tmp_path / "template_filled.docx"
                asyncio.run(
                    screen.do_fill(
                        notice, None, template, use_existing=False
                    )
                )

        mock_extractor_cls.return_value.extract_all.assert_called_once_with(
            notice, None
        )
        mock_fill.assert_called_once_with(template, {"A": "1"}, None)
    finally:
        patcher.stop()


def test_doc_do_process_extracts_fills_and_submits(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-123"
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        template = tmp_path / "template.docx"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {
                "WITNESS_NAME": "Jane Doe"
            }
            with patch("lexiflow.tui.fill_template") as mock_fill:
                mock_fill.return_value = tmp_path / "template_filled.docx"
                external_id = asyncio.run(
                    screen.do_process(notice, pbs, template, "revai")
                )

        assert external_id == "ext-123"
        mock_fill.assert_called_once_with(
            template, {"WITNESS_NAME": "Jane Doe"}, None
        )
        screen.app.transcriptor.submit_transcription.assert_awaited_once_with(
            5, "revai", additional_vocabulary=["Jane", "Doe"]
        )
    finally:
        patcher.stop()


def test_doc_do_process_raises_without_template(tmp_path):
    """Process combines Extract+Fill+Transcribe -- unlike the
    standalone Transcribe action, a template is mandatory even when
    metadata is available."""
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        with patch("lexiflow.tui.MetadataExtractor"):
            with pytest.raises(ValueError, match="Select a template"):
                asyncio.run(screen.do_process(notice, pbs, None, "revai"))
    finally:
        patcher.stop()


def test_doc_do_transcribe_plain_submit_without_metadata(tmp_path):
    """No notice/PBS/template/existing metadata.json at all --
    Transcribe must still work as a plain submit, independent of the
    other 3 actions."""
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-1"
        external_id = asyncio.run(
            screen.do_transcribe("revai", use_existing=False)
        )

        screen.app.transcriptor.submit_transcription.assert_awaited_once_with(
            5, "revai", additional_vocabulary=None
        )
        assert external_id == "ext-1"
        assert screen.job_data["provider"] == "revai"
        assert screen.job_data["external_job_id"] == "ext-1"
        assert screen.job_data["transcription_status"] == "in_progress"
    finally:
        patcher.stop()


def test_doc_do_transcribe_uses_existing_metadata_vocabulary(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"WITNESS_NAME": "Jane Doe"})
    )
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-1"
        asyncio.run(screen.do_transcribe("revai", use_existing=True))

        screen.app.transcriptor.submit_transcription.assert_awaited_once_with(
            5, "revai", additional_vocabulary=["Jane", "Doe"]
        )
    finally:
        patcher.stop()


def test_doc_do_transcribe_propagates_submit_errors(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.side_effect = ValueError(
            "boom"
        )
        with pytest.raises(ValueError, match="boom"):
            asyncio.run(
                screen.do_transcribe("revai", use_existing=False)
            )
    finally:
        patcher.stop()


def test_doc_do_transcribe_clears_last_error_on_success(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "transcription_last_error": "previous failure",
        }
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-1"
        asyncio.run(screen.do_transcribe("revai", use_existing=False))
        assert screen.job_data["transcription_last_error"] is None
    finally:
        patcher.stop()


def test_doc_do_process_reuses_existing_metadata_without_reextracting(
    tmp_path,
):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"WITNESS_NAME": "Jane Doe"})
    )
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-123"
        template = tmp_path / "template.docx"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            with patch("lexiflow.tui.fill_template") as mock_fill:
                mock_fill.return_value = tmp_path / "template_filled.docx"
                external_id = asyncio.run(
                    screen.do_process(
                        None, None, template, "revai", use_existing=True
                    )
                )

        mock_extractor_cls.assert_not_called()
        assert external_id == "ext-123"
        mock_fill.assert_called_once_with(
            template, {"WITNESS_NAME": "Jane Doe"}, None
        )
        screen.app.transcriptor.submit_transcription.assert_awaited_once_with(
            5, "revai", additional_vocabulary=["Jane", "Doe"]
        )
    finally:
        patcher.stop()


def test_doc_do_process_raises_when_template_given_without_metadata(
    tmp_path,
):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        template = tmp_path / "template.docx"
        with pytest.raises(ValueError, match="Select a notice and/or"):
            asyncio.run(screen.do_process(None, None, template, "revai"))
    finally:
        patcher.stop()


def test_doc_format_info_no_metadata(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        assert "No metadata.json" in screen._format_info()
    finally:
        patcher.stop()


def test_doc_format_info_with_metadata(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    (tmp_path / "metadata.json").write_text("{}")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        assert "metadata.json found" in screen._format_info()
    finally:
        patcher.stop()


def test_doc_do_poll_updates_status_when_present(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
        }
    )
    try:
        screen.app.transcriptor.poll_transcription_status.return_value = (
            "transcribed"
        )
        status = asyncio.run(screen.do_poll())

        screen.app.transcriptor.poll_transcription_status.assert_awaited_once_with(
            5
        )
        assert status == "transcribed"
        assert screen.job_data["transcription_status"] == "transcribed"
    finally:
        patcher.stop()


def test_doc_do_poll_leaves_job_data_unchanged_when_none(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "transcription_status": "in_progress",
        }
    )
    try:
        screen.app.transcriptor.poll_transcription_status.return_value = None
        status = asyncio.run(screen.do_poll())

        assert status is None
        assert screen.job_data["transcription_status"] == "in_progress"
    finally:
        patcher.stop()


def test_doc_do_poll_records_last_polled_at_and_clears_error(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
            "transcription_last_error": "previous failure",
        }
    )
    try:
        screen.app.transcriptor.poll_transcription_status.return_value = (
            "transcribed"
        )
        asyncio.run(screen.do_poll())
        assert screen.job_data["transcription_last_polled_at"]
        assert screen.job_data["transcription_last_error"] is None
    finally:
        patcher.stop()


def test_doc_do_fetch_updates_status_and_returns_path(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
        }
    )
    try:
        transcript_path = tmp_path / "TX001_transcript.txt"
        screen.app.transcriptor.fetch_transcript.return_value = transcript_path
        result = asyncio.run(screen.do_fetch())

        screen.app.transcriptor.fetch_transcript.assert_awaited_once_with(5)
        assert result == transcript_path
        assert screen.job_data["transcription_status"] == "transcribed"
    finally:
        patcher.stop()


def test_doc_do_fetch_clears_last_error_on_success(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
            "transcription_last_error": "previous failure",
        }
    )
    try:
        screen.app.transcriptor.fetch_transcript.return_value = (
            "/tmp/x_transcript.txt"
        )
        asyncio.run(screen.do_fetch())
        assert screen.job_data["transcription_last_error"] is None
    finally:
        patcher.stop()


def test_doc_format_info_shows_not_yet_submitted(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        assert "Not yet submitted" in screen._format_info()
    finally:
        patcher.stop()


def test_doc_format_info_shows_provider_details(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
            "transcription_status": "in_progress",
        }
    )
    try:
        info = screen._format_info()
        assert "revai" in info
        assert "ext-1" in info
        assert "in_progress" in info
    finally:
        patcher.stop()


def test_doc_format_info_shows_last_polled_at(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
            "transcription_status": "in_progress",
            "transcription_last_polled_at": "2023-01-01T12:00:00",
        }
    )
    try:
        info = screen._format_info()
        assert "2023-01-01T12:00:00" in info
    finally:
        patcher.stop()


def test_doc_format_info_shows_last_error(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
            "transcription_status": "in_progress",
            "transcription_last_error": "Connection timed out",
        }
    )
    try:
        info = screen._format_info()
        assert "Connection timed out" in info
    finally:
        patcher.stop()


def test_doc_format_info_omits_error_line_when_none(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("x")
    screen, patcher = _document_processing_screen_with_mock_app(
        {
            "id": 5,
            "job_path": str(job_path),
            "provider": "revai",
            "external_job_id": "ext-1",
            "transcription_status": "in_progress",
            "transcription_last_error": None,
        }
    )
    try:
        info = screen._format_info()
        assert "Last error" not in info
    finally:
        patcher.stop()


# -------- worker dispatch (fire-and-forget button handlers) --------


def test_doc_extract_worker_success_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {
                "A": "1"
            }
            asyncio.run(screen._extract_worker(notice, pbs))

        screen.app.notify.assert_called_once_with(
            "Metadata extracted and saved."
        )
    finally:
        patcher.stop()


def test_doc_extract_worker_error_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.side_effect = (
                RuntimeError("boom")
            )
            asyncio.run(screen._extract_worker(notice, pbs))

        screen.app.notify.assert_called_once_with(
            "Error extracting metadata: boom", severity="error"
        )
    finally:
        patcher.stop()


def test_doc_extract_button_dispatches_via_run_worker():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(
            type(screen), "_selected_path", return_value=Path("/tmp/notice.pdf")
        ):
            screen.on_extract_pressed()

        screen.run_worker.assert_called_once()
        (coro,), _ = screen.run_worker.call_args
        assert asyncio.iscoroutine(coro)
        coro.close()
    finally:
        patcher.stop()


def test_doc_extract_button_validates_before_dispatch():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(type(screen), "_selected_path", return_value=None):
            screen.on_extract_pressed()

        screen.run_worker.assert_not_called()
        screen.app.notify.assert_called_once_with(
            "Select a notice and/or a PBS file.", severity="error"
        )
    finally:
        patcher.stop()


def test_doc_fill_worker_success_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    (tmp_path / "metadata.json").write_text(json.dumps({"A": "1"}))
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        template = tmp_path / "template.docx"
        result_path = tmp_path / "template_filled.docx"
        with patch("lexiflow.tui.fill_template") as mock_fill:
            mock_fill.return_value = result_path
            asyncio.run(
                screen._fill_worker(None, None, template, use_existing=True)
            )

        screen.app.notify.assert_called_once_with(
            f"Filled template saved to {result_path}"
        )
    finally:
        patcher.stop()


def test_doc_fill_worker_error_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        template = tmp_path / "template.docx"
        asyncio.run(
            screen._fill_worker(None, None, template, use_existing=False)
        )

        screen.app.notify.assert_called_once()
        args, kwargs = screen.app.notify.call_args
        assert "Error filling template" in args[0]
        assert kwargs.get("severity") == "error"
    finally:
        patcher.stop()


def test_doc_fill_button_dispatches_via_run_worker():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(
            type(screen),
            "_selected_path",
            return_value=Path("/tmp/template.docx"),
        ):
            with patch.object(
                DocumentProcessingScreen,
                "query_one",
                return_value=MagicMock(value=True),
            ):
                screen.on_fill_pressed()

        screen.run_worker.assert_called_once()
        (coro,), _ = screen.run_worker.call_args
        assert asyncio.iscoroutine(coro)
        coro.close()
    finally:
        patcher.stop()


def test_doc_fill_button_validates_template_before_dispatch():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(type(screen), "_selected_path", return_value=None):
            screen.on_fill_pressed()

        screen.run_worker.assert_not_called()
        screen.app.notify.assert_called_once_with(
            "Select a template.", severity="error"
        )
    finally:
        patcher.stop()


def test_doc_transcribe_worker_success_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-1"
        asyncio.run(screen._transcribe_worker("revai", use_existing=False))

        screen.app.notify.assert_called_once_with(
            "Submitted to revai: ext-1"
        )
    finally:
        patcher.stop()


def test_doc_transcribe_worker_error_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.side_effect = (
            ValueError("boom")
        )
        asyncio.run(screen._transcribe_worker("revai", use_existing=False))

        screen.app.notify.assert_called_once_with(
            "Error transcribing: boom", severity="error"
        )
    finally:
        patcher.stop()


def test_doc_transcribe_button_dispatches_via_run_worker():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(
            DocumentProcessingScreen,
            "query_one",
            return_value=MagicMock(value="revai"),
        ):
            screen.on_transcribe_pressed()

        screen.run_worker.assert_called_once()
        (coro,), _ = screen.run_worker.call_args
        assert asyncio.iscoroutine(coro)
        coro.close()
    finally:
        patcher.stop()


def test_doc_transcribe_button_validates_provider_before_dispatch():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(
            DocumentProcessingScreen,
            "query_one",
            return_value=MagicMock(value=Select.BLANK),
        ):
            screen.on_transcribe_pressed()

        screen.run_worker.assert_not_called()
        screen.app.notify.assert_called_once_with(
            "Select a provider.", severity="error"
        )
    finally:
        patcher.stop()


def test_doc_process_worker_success_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-1"
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        template = tmp_path / "template.docx"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {}
            with patch("lexiflow.tui.fill_template"):
                asyncio.run(
                    screen._process_worker(
                        notice, pbs, template, "revai", use_existing=False
                    )
                )

        screen.app.notify.assert_called_once_with(
            "Submitted to revai: ext-1"
        )
    finally:
        patcher.stop()


def test_doc_process_worker_error_notifies(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        asyncio.run(
            screen._process_worker(None, None, None, "revai")
        )

        screen.app.notify.assert_called_once_with(
            "Error processing: Select a template.", severity="error"
        )
    finally:
        patcher.stop()


def test_doc_process_button_dispatches_via_run_worker():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(
            type(screen),
            "_selected_path",
            return_value=Path("/tmp/template.docx"),
        ):
            with patch.object(
                DocumentProcessingScreen,
                "query_one",
                return_value=MagicMock(value="revai"),
            ):
                screen.on_process_pressed()

        screen.run_worker.assert_called_once()
        (coro,), _ = screen.run_worker.call_args
        assert asyncio.iscoroutine(coro)
        coro.close()
    finally:
        patcher.stop()


def test_doc_process_button_validates_template_before_dispatch():
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": "/tmp/audio.mp3"}
    )
    screen.run_worker = MagicMock()
    try:
        with patch.object(type(screen), "_selected_path", return_value=None):
            screen.on_process_pressed()

        screen.run_worker.assert_not_called()
        screen.app.notify.assert_called_once_with(
            "Select a template.", severity="error"
        )
    finally:
        patcher.stop()


def test_job_context_menu_transcribe_job_pushes_document_processing_screen():
    job_data = {"id": 5, "job_number": "J1", "job_path": "/tmp/audio.mp3"}
    menu = JobContextMenu(job_data)
    patcher = patch.object(type(menu), "app", new_callable=PropertyMock)
    mock_app_prop = patcher.start()
    mock_app_prop.return_value = MagicMock()
    try:
        menu.handle_action("transcribe-job")

        menu.app.push_screen.assert_called_once()
        pushed_screen, callback = menu.app.push_screen.call_args.args
        assert isinstance(pushed_screen, DocumentProcessingScreen)
        assert pushed_screen.job_data == job_data
        assert callback == menu.check_edit
    finally:
        patcher.stop()


def _table_with_mock_app(table):
    table, patcher = _screen_with_mock_app(table)
    table.app.transcriptor = AsyncMock()
    # get_transcript_path is sync on the real Transcriptor; default to a
    # path that doesn't exist so tests reach the poll/fetch logic unless
    # they deliberately override this to exercise the skip-if-exists path.
    table.app.transcriptor.get_transcript_path = MagicMock(
        return_value=Path("/nonexistent/TX001_transcript.txt")
    )
    return table, patcher


def test_dashboard_check_and_fetch_no_job_selected(tmp_path):
    dashboard, patcher = _table_with_mock_app(Dashboard())
    try:
        asyncio.run(dashboard._check_and_fetch_transcript())

        dashboard.app.notify.assert_called_once_with(
            "No job selected!", severity="error"
        )
        dashboard.app.transcriptor.poll_transcription_status.assert_not_called()
    finally:
        patcher.stop()


def test_dashboard_check_and_fetch_skips_poll_when_already_fetched(tmp_path):
    dashboard, patcher = _table_with_mock_app(Dashboard())
    try:
        dashboard.selected_items = [5]
        transcript_path = tmp_path / "TX001_transcript.txt"
        transcript_path.write_text("already here")
        dashboard.app.transcriptor.get_transcript_path = MagicMock(
            return_value=transcript_path
        )
        dashboard.refresh_table = MagicMock()

        asyncio.run(dashboard._check_and_fetch_transcript())

        dashboard.app.transcriptor.poll_transcription_status.assert_not_called()
        dashboard.app.transcriptor.fetch_transcript.assert_not_called()
        dashboard.app.notify.assert_called_once_with(
            f"Transcript already fetched: {transcript_path}"
        )
    finally:
        patcher.stop()


def test_dashboard_check_and_fetch_no_transcription_in_progress(tmp_path):
    dashboard, patcher = _table_with_mock_app(Dashboard())
    try:
        dashboard.selected_items = [5]
        dashboard.app.transcriptor.poll_transcription_status.return_value = (
            None
        )
        dashboard.refresh_table = MagicMock()

        asyncio.run(dashboard._check_and_fetch_transcript())

        dashboard.app.transcriptor.poll_transcription_status.assert_awaited_once_with(
            5
        )
        dashboard.app.transcriptor.fetch_transcript.assert_not_called()
        dashboard.app.notify.assert_called_once_with(
            "No transcription in progress, or the provider poll failed.",
            severity="warning",
        )
        dashboard.refresh_table.assert_called_once()
    finally:
        patcher.stop()


def test_dashboard_check_and_fetch_reports_status_when_not_ready(tmp_path):
    dashboard, patcher = _table_with_mock_app(Dashboard())
    try:
        dashboard.selected_items = [5]
        dashboard.app.transcriptor.poll_transcription_status.return_value = (
            "in_progress"
        )
        dashboard.refresh_table = MagicMock()

        asyncio.run(dashboard._check_and_fetch_transcript())

        dashboard.app.transcriptor.fetch_transcript.assert_not_called()
        dashboard.app.notify.assert_called_once_with("Status: in_progress")
        dashboard.refresh_table.assert_called_once()
    finally:
        patcher.stop()


def test_dashboard_check_and_fetch_fetches_when_transcribed(tmp_path):
    dashboard, patcher = _table_with_mock_app(Dashboard())
    try:
        dashboard.selected_items = [5]
        dashboard.app.transcriptor.poll_transcription_status.return_value = (
            "transcribed"
        )
        transcript_path = tmp_path / "TX001_transcript.txt"
        dashboard.app.transcriptor.fetch_transcript.return_value = (
            transcript_path
        )
        dashboard.refresh_table = MagicMock()

        asyncio.run(dashboard._check_and_fetch_transcript())

        dashboard.app.transcriptor.fetch_transcript.assert_awaited_once_with(
            5
        )
        dashboard.app.notify.assert_called_once_with(
            f"Transcript saved to {transcript_path}"
        )
        assert dashboard.refresh_table.call_count == 1
    finally:
        patcher.stop()


def test_dashboard_check_and_fetch_poll_error_notifies(tmp_path):
    dashboard, patcher = _table_with_mock_app(Dashboard())
    try:
        dashboard.selected_items = [5]
        dashboard.app.transcriptor.poll_transcription_status.side_effect = (
            ValueError("boom")
        )

        asyncio.run(dashboard._check_and_fetch_transcript())

        dashboard.app.notify.assert_called_once_with(
            "Error polling status: boom", severity="error"
        )
        dashboard.app.transcriptor.fetch_transcript.assert_not_called()
    finally:
        patcher.stop()


def test_dashboard_action_check_and_fetch_schedules_worker():
    dashboard = Dashboard()
    dashboard.run_worker = MagicMock()

    dashboard.action_check_and_fetch()

    dashboard.run_worker.assert_called_once()
    (coro,), _ = dashboard.run_worker.call_args
    assert asyncio.iscoroutine(coro)
    coro.close()


def test_dashboard_check_fetch_button_schedules_worker():
    dashboard = Dashboard()
    dashboard.run_worker = MagicMock()

    dashboard.on_dash_check_fetch()

    dashboard.run_worker.assert_called_once()
    (coro,), _ = dashboard.run_worker.call_args
    assert asyncio.iscoroutine(coro)
    coro.close()


def test_jobs_table_check_and_fetch_no_job_selected(tmp_path):
    jobs_table, patcher = _table_with_mock_app(JobsTable())
    try:
        asyncio.run(jobs_table._check_and_fetch_transcript())

        jobs_table.app.notify.assert_called_once_with(
            "No job selected!", severity="error"
        )
        jobs_table.app.transcriptor.poll_transcription_status.assert_not_called()
    finally:
        patcher.stop()


def test_jobs_table_check_and_fetch_skips_poll_when_already_fetched(
    tmp_path,
):
    jobs_table, patcher = _table_with_mock_app(JobsTable())
    try:
        jobs_table.selected_items = [5]
        transcript_path = tmp_path / "TX001_transcript.txt"
        transcript_path.write_text("already here")
        jobs_table.app.transcriptor.get_transcript_path = MagicMock(
            return_value=transcript_path
        )
        jobs_table.refresh_table = MagicMock()

        asyncio.run(jobs_table._check_and_fetch_transcript())

        jobs_table.app.transcriptor.poll_transcription_status.assert_not_called()
        jobs_table.app.transcriptor.fetch_transcript.assert_not_called()
        jobs_table.app.notify.assert_called_once_with(
            f"Transcript already fetched: {transcript_path}"
        )
    finally:
        patcher.stop()


def test_jobs_table_check_and_fetch_no_transcription_in_progress(tmp_path):
    jobs_table, patcher = _table_with_mock_app(JobsTable())
    try:
        jobs_table.selected_items = [5]
        jobs_table.app.transcriptor.poll_transcription_status.return_value = (
            None
        )
        jobs_table.refresh_table = MagicMock()

        asyncio.run(jobs_table._check_and_fetch_transcript())

        jobs_table.app.transcriptor.poll_transcription_status.assert_awaited_once_with(
            5
        )
        jobs_table.app.transcriptor.fetch_transcript.assert_not_called()
        jobs_table.app.notify.assert_called_once_with(
            "No transcription in progress, or the provider poll failed.",
            severity="warning",
        )
        jobs_table.refresh_table.assert_called_once()
    finally:
        patcher.stop()


def test_jobs_table_check_and_fetch_reports_status_when_not_ready(tmp_path):
    jobs_table, patcher = _table_with_mock_app(JobsTable())
    try:
        jobs_table.selected_items = [5]
        jobs_table.app.transcriptor.poll_transcription_status.return_value = (
            "in_progress"
        )
        jobs_table.refresh_table = MagicMock()

        asyncio.run(jobs_table._check_and_fetch_transcript())

        jobs_table.app.transcriptor.fetch_transcript.assert_not_called()
        jobs_table.app.notify.assert_called_once_with("Status: in_progress")
        jobs_table.refresh_table.assert_called_once()
    finally:
        patcher.stop()


def test_jobs_table_check_and_fetch_fetches_when_transcribed(tmp_path):
    jobs_table, patcher = _table_with_mock_app(JobsTable())
    try:
        jobs_table.selected_items = [5]
        jobs_table.app.transcriptor.poll_transcription_status.return_value = (
            "transcribed"
        )
        transcript_path = tmp_path / "TX001_transcript.txt"
        jobs_table.app.transcriptor.fetch_transcript.return_value = (
            transcript_path
        )
        jobs_table.refresh_table = MagicMock()

        asyncio.run(jobs_table._check_and_fetch_transcript())

        jobs_table.app.transcriptor.fetch_transcript.assert_awaited_once_with(
            5
        )
        jobs_table.app.notify.assert_called_once_with(
            f"Transcript saved to {transcript_path}"
        )
        assert jobs_table.refresh_table.call_count == 1
    finally:
        patcher.stop()


def test_jobs_table_check_and_fetch_poll_error_notifies(tmp_path):
    jobs_table, patcher = _table_with_mock_app(JobsTable())
    try:
        jobs_table.selected_items = [5]
        jobs_table.app.transcriptor.poll_transcription_status.side_effect = (
            ValueError("boom")
        )

        asyncio.run(jobs_table._check_and_fetch_transcript())

        jobs_table.app.notify.assert_called_once_with(
            "Error polling status: boom", severity="error"
        )
        jobs_table.app.transcriptor.fetch_transcript.assert_not_called()
    finally:
        patcher.stop()


def test_jobs_table_action_check_and_fetch_schedules_worker():
    jobs_table = JobsTable()
    jobs_table.run_worker = MagicMock()

    jobs_table.action_check_and_fetch()

    jobs_table.run_worker.assert_called_once()
    (coro,), _ = jobs_table.run_worker.call_args
    assert asyncio.iscoroutine(coro)
    coro.close()


def test_jobs_table_check_fetch_button_schedules_worker():
    jobs_table = JobsTable()
    jobs_table.run_worker = MagicMock()

    jobs_table.on_jobs_check_fetch()

    jobs_table.run_worker.assert_called_once()
    (coro,), _ = jobs_table.run_worker.call_args
    assert asyncio.iscoroutine(coro)
    coro.close()


def test_dashboard_action_transcribe_job_pushes_document_processing_screen():
    dashboard = Dashboard()
    patcher = patch.object(
        type(dashboard), "app", new_callable=PropertyMock
    )
    mock_app_prop = patcher.start()
    mock_app_prop.return_value = MagicMock()
    try:
        job_data = {"id": 5, "job_number": "J1", "job_path": "/tmp/audio.mp3"}
        dashboard.app.transcriptor.api.get_jobs.return_value = [job_data]
        dashboard.selected_items = [5]

        dashboard.action_transcribe_job()

        dashboard.app.push_screen.assert_called_once()
        pushed_screen, _ = dashboard.app.push_screen.call_args.args
        assert isinstance(pushed_screen, DocumentProcessingScreen)
        assert pushed_screen.job_data == job_data
    finally:
        patcher.stop()


def test_jobs_table_action_transcribe_job_pushes_document_processing_screen():
    jobs_table = JobsTable()
    patcher = patch.object(
        type(jobs_table), "app", new_callable=PropertyMock
    )
    mock_app_prop = patcher.start()
    mock_app_prop.return_value = MagicMock()
    try:
        job_data = {"id": 5, "job_number": "J1", "job_path": "/tmp/audio.mp3"}
        jobs_table.app.transcriptor.api.get_jobs.return_value = [job_data]
        jobs_table.selected_items = [5]

        jobs_table.action_transcribe_job()

        jobs_table.app.push_screen.assert_called_once()
        pushed_screen, _ = jobs_table.app.push_screen.call_args.args
        assert isinstance(pushed_screen, DocumentProcessingScreen)
        assert pushed_screen.job_data == job_data
    finally:
        patcher.stop()


def test_job_context_menu_open_file_manager_calls_utility(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    job_data = {"id": 5, "job_number": "J1", "job_path": str(job_path)}
    menu = JobContextMenu(job_data)
    patcher = patch.object(type(menu), "app", new_callable=PropertyMock)
    mock_app_prop = patcher.start()
    mock_app_prop.return_value = MagicMock()
    try:
        with (
            patch(
                "lexiflow.tui.open_in_file_manager"
            ) as mock_open_in_file_manager,
            patch.object(menu, "dismiss"),
        ):
            menu.handle_action("open-file-manager")
        mock_open_in_file_manager.assert_called_once_with(
            job_path, suspend_cm=menu.app.suspend
        )
    finally:
        patcher.stop()
