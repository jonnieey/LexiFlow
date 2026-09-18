import zipfile
from unittest.mock import MagicMock, PropertyMock, patch

from lexiflow.tui import AddJobScreen


def _screen_with_mock_app():
    screen = AddJobScreen()
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
