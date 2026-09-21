import subprocess
from unittest.mock import patch

from lexiflow.utils.system_open import open_in_file_manager


def test_open_in_file_manager_linux(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)
    mock_popen.assert_called_once_with(
        ["xdg-open", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_open_in_file_manager_windows(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)
    mock_popen.assert_called_once_with(
        ["explorer", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_open_in_file_manager_macos(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)
    mock_popen.assert_called_once_with(
        ["open", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_open_in_file_manager_resolves_file_to_parent_dir(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("sys.platform", "linux")
    job_file = tmp_path / "audio.mp3"
    job_file.write_text("fake audio")
    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(job_file)
    mock_popen.assert_called_once_with(
        ["xdg-open", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
