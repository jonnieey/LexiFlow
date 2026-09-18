import asyncio
import zipfile
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from lexiflow.tui import AddJobScreen, TranscriptionScreen


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
