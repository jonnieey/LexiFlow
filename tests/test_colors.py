from unittest.mock import MagicMock

import pytest

# Try importing. If it fails due to missing dependencies (like cmd2), we skip
try:
    from lexiflow.colors import CmdLineApp
except ImportError:
    pytest.skip(
        "cmd2 not installed or transcriptor.colors not found",
        allow_module_level=True,
    )


def test_colors_initialization():
    app = CmdLineApp()
    assert app.allow_style is not None


def test_do_speak():
    app = CmdLineApp()
    # Mock poutput to avoid printing to stdout
    app.poutput = MagicMock()

    # Use onecmd to bypass decorator complexity
    app.onecmd("speak hello world")
    app.poutput.assert_called()


def test_do_timetravel():
    app = CmdLineApp()
    app.perror = MagicMock()
    app.do_timetravel(None)
    app.perror.assert_called()
