import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, ContextManager, List, Optional, Sequence, Tuple

_OPENERS = {
    "win32": "explorer",
    "darwin": "open",
}

# Terminal (TUI) file managers that must run inside a terminal emulator.
_TUI_MANAGERS = {
    "clifm",
    "lf",
    "ranger",
    "nnn",
    "vifm",
    "yazi",
    "mc",
    "joshuto",
    "broot",
}

# (executable, args needed to run a command inside it)
_TERMINALS: Tuple[Tuple[str, List[str]], ...] = (
    ("kitty", ["-e"]),
    ("alacritty", ["-e"]),
    ("wezterm", ["start", "--"]),
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("foot", []),
    ("xterm", ["-e"]),
)

_FIELD_CODES = {"%f", "%F", "%u", "%U", "%i", "%c", "%k"}


def _settings():
    from lexiflow.config import settings

    return settings


def _parse_desktop_field_codes(exec_line: str) -> List[str]:
    return [
        part for part in shlex.split(exec_line) if part not in _FIELD_CODES
    ]


def _desktop_file_path(name: str) -> Optional[Path]:
    data_home = os.environ.get("XDG_DATA_HOME") or str(
        Path.home() / ".local" / "share"
    )
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for base in [data_home, *data_dirs.split(":")]:
        candidate = Path(base) / "applications" / name
        if candidate.is_file():
            return candidate
    return None


def _parse_desktop_entry(path: Path) -> Tuple[Optional[List[str]], bool]:
    exec_line: Optional[str] = None
    terminal = False
    section: Optional[str] = None
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Desktop Entry":
            continue
        if line.startswith("Exec="):
            exec_line = line[len("Exec="):]
        elif line.startswith("Terminal="):
            terminal = line[len("Terminal="):].strip().lower() == "true"
    if not exec_line:
        return None, terminal
    return _parse_desktop_field_codes(exec_line), terminal


def _detect_xdg_manager() -> Tuple[Optional[List[str]], bool]:
    if not shutil.which("xdg-mime"):
        return None, False
    try:
        result = subprocess.run(
            ["xdg-mime", "query", "default", "inode/directory"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None, False
    desktop_name = result.stdout.strip()
    if not desktop_name:
        return None, False
    desktop_path = _desktop_file_path(desktop_name)
    if desktop_path is None:
        return None, False
    return _parse_desktop_entry(desktop_path)


def _resolve_manager() -> Tuple[Optional[List[str]], bool, bool]:
    """Return (argv, is_tui, explicit) for the configured/detected manager."""
    configured = (_settings().FILE_MANAGER or "").strip()
    if configured:
        argv = shlex.split(configured)
        if argv:
            return argv, Path(argv[0]).name in _TUI_MANAGERS, True
    if sys.platform.startswith("linux"):
        argv, terminal_required = _detect_xdg_manager()
        if argv:
            is_tui = terminal_required or Path(argv[0]).name in _TUI_MANAGERS
            return argv, is_tui, False
    return None, False, False


def _resolve_terminal() -> Optional[List[str]]:
    configured = (_settings().TERMINAL or "").strip()
    if configured:
        argv = shlex.split(configured)
        if argv:
            return argv
    for name, args in _TERMINALS:
        if shutil.which(name):
            return [name, *args]
    return None


def _default_opener() -> str:
    return _OPENERS.get(sys.platform, "xdg-open")


def _spawn_detached(argv: Sequence[str]) -> None:
    subprocess.Popen(
        list(argv),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_in_place(
    command: Sequence[str],
    suspend_cm: Optional[Callable[[], ContextManager]],
) -> None:
    if suspend_cm is not None:
        with suspend_cm():
            subprocess.run(list(command), check=False)
    else:
        subprocess.run(list(command), check=False)


def open_in_file_manager(
    path: Path,
    *,
    suspend_cm: Optional[Callable[[], ContextManager]] = None,
) -> None:
    """Open the given path's directory in a file manager.

    Terminal-based managers (e.g. clifm) are launched inside a terminal
    emulator so they get a real TTY. Without an emulator they are run in
    place, releasing the caller's terminal via ``suspend_cm`` when given.
    GUI managers and platform defaults are spawned detached.
    """
    path = Path(path)
    target_dir = path if path.is_dir() else path.parent
    manager, is_tui, explicit = _resolve_manager()

    if manager and is_tui:
        command = [*manager, str(target_dir)]
        terminal = _resolve_terminal()
        if terminal is not None:
            _spawn_detached([*terminal, *command])
        else:
            _run_in_place(command, suspend_cm)
        return

    if explicit and manager:
        _spawn_detached([*manager, str(target_dir)])
        return

    _spawn_detached([_default_opener(), str(target_dir)])
