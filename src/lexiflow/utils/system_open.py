import subprocess
import sys
from pathlib import Path

_OPENERS = {
    "win32": "explorer",
    "darwin": "open",
}


def open_in_file_manager(path: Path) -> None:
    """Launch the platform's file manager on the given path's directory.

    Runs as a detached process so it isn't a child the caller waits on
    or that dies with the caller.
    """
    path = Path(path)
    target_dir = path if path.is_dir() else path.parent
    opener = _OPENERS.get(sys.platform, "xdg-open")
    subprocess.Popen(
        [opener, str(target_dir)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
