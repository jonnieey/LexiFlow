import subprocess
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lexiflow.utils import system_open
from lexiflow.utils.system_open import open_in_file_manager


@pytest.fixture
def fake_settings(monkeypatch):
    def _apply(file_manager="", terminal=""):
        monkeypatch.setattr(
            system_open,
            "_settings",
            lambda: SimpleNamespace(
                FILE_MANAGER=file_manager, TERMINAL=terminal
            ),
        )

    return _apply


@pytest.fixture(autouse=True)
def no_detected_manager(monkeypatch):
    monkeypatch.setattr(
        system_open, "_detect_xdg_manager", lambda: (None, False)
    )


def test_tui_manager_spawns_in_terminal(tmp_path, monkeypatch, fake_settings):
    monkeypatch.setattr("sys.platform", "linux")
    fake_settings(file_manager="clifm", terminal="kitty -e")

    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)

    mock_popen.assert_called_once_with(
        ["kitty", "-e", "clifm", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_tui_manager_without_terminal_runs_in_place(
    tmp_path, monkeypatch, fake_settings
):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(system_open.shutil, "which", lambda _name: None)
    fake_settings(file_manager="clifm", terminal="")

    with (
        patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen,
        patch("lexiflow.utils.system_open.subprocess.run") as mock_run,
    ):
        open_in_file_manager(tmp_path)

    mock_popen.assert_not_called()
    mock_run.assert_called_once_with(["clifm", str(tmp_path)], check=False)


def test_tui_manager_in_place_enters_suspend_context(
    tmp_path, monkeypatch, fake_settings
):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(system_open.shutil, "which", lambda _name: None)
    fake_settings(file_manager="clifm", terminal="")

    entered = []

    @contextmanager
    def suspend_cm():
        entered.append(True)
        yield

    with patch("lexiflow.utils.system_open.subprocess.run"):
        open_in_file_manager(tmp_path, suspend_cm=suspend_cm)

    assert entered == [True]


def test_detected_tui_manager_is_wrapped_in_terminal(
    tmp_path, monkeypatch, fake_settings
):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(
        system_open, "_detect_xdg_manager", lambda: (["clifm"], True)
    )
    fake_settings(terminal="alacritty -e")

    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)

    mock_popen.assert_called_once_with(
        ["alacritty", "-e", "clifm", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_detected_gui_manager_uses_default_opener(
    tmp_path, monkeypatch, fake_settings
):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(
        system_open, "_detect_xdg_manager", lambda: (["thunar"], False)
    )
    fake_settings()

    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)

    mock_popen.assert_called_once_with(
        ["xdg-open", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_explicit_gui_manager_spawned_directly(
    tmp_path, monkeypatch, fake_settings
):
    monkeypatch.setattr("sys.platform", "linux")
    fake_settings(file_manager="thunar")

    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)

    mock_popen.assert_called_once_with(
        ["thunar", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_open_in_file_manager_linux_fallback(tmp_path, monkeypatch, fake_settings):
    monkeypatch.setattr("sys.platform", "linux")
    fake_settings()

    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)

    mock_popen.assert_called_once_with(
        ["xdg-open", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_open_in_file_manager_windows(tmp_path, monkeypatch, fake_settings):
    monkeypatch.setattr("sys.platform", "win32")
    fake_settings()

    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)

    mock_popen.assert_called_once_with(
        ["explorer", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_open_in_file_manager_macos(tmp_path, monkeypatch, fake_settings):
    monkeypatch.setattr("sys.platform", "darwin")
    fake_settings()

    with patch("lexiflow.utils.system_open.subprocess.Popen") as mock_popen:
        open_in_file_manager(tmp_path)

    mock_popen.assert_called_once_with(
        ["open", str(tmp_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_open_in_file_manager_resolves_file_to_parent_dir(
    tmp_path, monkeypatch, fake_settings
):
    monkeypatch.setattr("sys.platform", "linux")
    fake_settings()
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


def test_parse_desktop_field_codes_strips_placeholders():
    assert system_open._parse_desktop_field_codes("clifm %F") == ["clifm"]
    assert system_open._parse_desktop_field_codes(
        "thunar --daemon %u"
    ) == ["thunar", "--daemon"]


def test_parse_desktop_entry_detects_terminal(tmp_path):
    desktop = tmp_path / "clifm.desktop"
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Exec=clifm %F\n"
        "Terminal=true\n"
    )

    argv, terminal = system_open._parse_desktop_entry(desktop)

    assert argv == ["clifm"]
    assert terminal is True
