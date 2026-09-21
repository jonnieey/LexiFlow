import asyncio
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from lexiflow.tui import (
    AddJobScreen,
    DocumentProcessingScreen,
    JobContextMenu,
    TranscriptionScreen,
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


# -------- TranscriptionScreen --------


def _transcription_screen_with_mock_app(job_data):
    screen, patcher = _screen_with_mock_app(TranscriptionScreen(job_data))
    screen.app.transcriptor = AsyncMock()
    return screen, patcher


def test_do_submit_updates_job_data_and_calls_transcriptor():
    screen, patcher = _transcription_screen_with_mock_app({"id": 5})
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-1"
        asyncio.run(screen.do_submit("revai"))

        screen.app.transcriptor.submit_transcription.assert_awaited_once_with(
            5, "revai"
        )
        assert screen.job_data["provider"] == "revai"
        assert screen.job_data["external_job_id"] == "ext-1"
        assert screen.job_data["transcription_status"] == "in_progress"
    finally:
        patcher.stop()


def test_do_submit_propagates_errors():
    screen, patcher = _transcription_screen_with_mock_app({"id": 5})
    try:
        screen.app.transcriptor.submit_transcription.side_effect = ValueError(
            "boom"
        )
        with pytest.raises(ValueError, match="boom"):
            asyncio.run(screen.do_submit("revai"))
    finally:
        patcher.stop()


def test_do_poll_updates_status_when_present():
    screen, patcher = _transcription_screen_with_mock_app(
        {"id": 5, "provider": "revai", "external_job_id": "ext-1"}
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


def test_do_poll_leaves_job_data_unchanged_when_none():
    screen, patcher = _transcription_screen_with_mock_app(
        {"id": 5, "transcription_status": "in_progress"}
    )
    try:
        screen.app.transcriptor.poll_transcription_status.return_value = None
        status = asyncio.run(screen.do_poll())

        assert status is None
        assert screen.job_data["transcription_status"] == "in_progress"
    finally:
        patcher.stop()


def test_do_fetch_updates_status_and_returns_path(tmp_path):
    screen, patcher = _transcription_screen_with_mock_app(
        {"id": 5, "provider": "revai", "external_job_id": "ext-1"}
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


def test_do_submit_clears_last_error_on_success():
    screen, patcher = _transcription_screen_with_mock_app(
        {"id": 5, "transcription_last_error": "previous failure"}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-1"
        asyncio.run(screen.do_submit("revai"))
        assert screen.job_data["transcription_last_error"] is None
    finally:
        patcher.stop()


def test_do_poll_records_last_polled_at_and_clears_error():
    screen, patcher = _transcription_screen_with_mock_app(
        {
            "id": 5,
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


def test_do_fetch_clears_last_error_on_success():
    screen, patcher = _transcription_screen_with_mock_app(
        {
            "id": 5,
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


def test_format_info_no_provider():
    screen, patcher = _transcription_screen_with_mock_app({"id": 5})
    try:
        assert "Not yet submitted" in screen._format_info()
    finally:
        patcher.stop()


def test_format_info_with_provider():
    screen, patcher = _transcription_screen_with_mock_app(
        {
            "id": 5,
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


def test_format_info_shows_last_polled_at():
    screen, patcher = _transcription_screen_with_mock_app(
        {
            "id": 5,
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


def test_format_info_shows_last_error():
    screen, patcher = _transcription_screen_with_mock_app(
        {
            "id": 5,
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


def test_format_info_omits_error_line_when_none():
    screen, patcher = _transcription_screen_with_mock_app(
        {
            "id": 5,
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
        with pytest.raises(ValueError, match="Select both a notice"):
            asyncio.run(screen.do_fill(None, None, template))
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


def test_doc_do_process_without_template_skips_fill(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        screen.app.transcriptor.submit_transcription.return_value = "ext-123"
        notice = tmp_path / "notice.pdf"
        pbs = tmp_path / "pbs.pdf"
        with patch("lexiflow.tui.MetadataExtractor") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_all.return_value = {}
            with patch("lexiflow.tui.fill_template") as mock_fill:
                asyncio.run(screen.do_process(notice, pbs, None, "revai"))

        mock_fill.assert_not_called()
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


def test_doc_do_process_raises_without_metadata_or_notice_pbs(tmp_path):
    job_path = tmp_path / "audio.mp3"
    job_path.write_text("fake audio")
    screen, patcher = _document_processing_screen_with_mock_app(
        {"id": 5, "job_path": str(job_path)}
    )
    try:
        with pytest.raises(ValueError, match="Select both a notice"):
            asyncio.run(screen.do_process(None, None, None, "revai"))
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


def test_job_context_menu_process_documents_pushes_screen():
    job_data = {"id": 5, "job_number": "J1", "job_path": "/tmp/audio.mp3"}
    menu = JobContextMenu(job_data)
    patcher = patch.object(type(menu), "app", new_callable=PropertyMock)
    mock_app_prop = patcher.start()
    mock_app_prop.return_value = MagicMock()
    try:
        menu.handle_action("process-documents")

        menu.app.push_screen.assert_called_once()
        pushed_screen, callback = menu.app.push_screen.call_args.args
        assert isinstance(pushed_screen, DocumentProcessingScreen)
        assert pushed_screen.job_data == job_data
        assert callback == menu.check_edit
    finally:
        patcher.stop()
