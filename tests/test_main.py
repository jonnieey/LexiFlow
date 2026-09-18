from unittest.mock import MagicMock, patch

import pytest

from lexiflow.main import main


@patch("lexiflow.main.sys.platform", "linux")
@patch("lexiflow.main.cli_main")
@patch("lexiflow.main.tui_main")
@patch("lexiflow.main.argparse.ArgumentParser.parse_args")
def test_main_cli_default(mock_parse_args, mock_tui_main, mock_cli_main):
    # Case 1: No arguments provided -> run CLI (default on Linux)
    mock_args = MagicMock()
    mock_args.command = None
    del mock_args.func  # Ensure func attribute is missing
    mock_parse_args.return_value = mock_args

    main()
    mock_cli_main.assert_called_once()
    mock_tui_main.assert_not_called()


@patch("lexiflow.main.sys.platform", "win32")
@patch("lexiflow.main.cli_main")
@patch("lexiflow.main.tui_main")
@patch("lexiflow.main.argparse.ArgumentParser.parse_args")
def test_main_tui_default_windows(
    mock_parse_args, mock_tui_main, mock_cli_main
):
    # Case 1b: No arguments provided -> run TUI (default on Windows)
    mock_args = MagicMock()
    mock_args.command = None
    del mock_args.func  # Ensure func attribute is missing
    mock_parse_args.return_value = mock_args

    main()
    mock_tui_main.assert_called_once()
    mock_cli_main.assert_not_called()


@patch("lexiflow.main.cli_main")
@patch("lexiflow.main.tui_main")
@patch("lexiflow.main.argparse.ArgumentParser.parse_args")
def test_main_cli_explicit(mock_parse_args, mock_tui_main, mock_cli_main):
    # Case 2: 'cli' command provided -> run CLI
    mock_args = MagicMock()
    mock_args.command = "cli"
    mock_args.func = mock_cli_main  # argparse sets the default func
    mock_args.cli_args = ["some", "args"]
    mock_parse_args.return_value = mock_args

    main()
    mock_cli_main.assert_called_with(argv=["some", "args"])
    mock_tui_main.assert_not_called()


@patch("lexiflow.main.cli_main")
@patch("lexiflow.main.tui_main")
@patch("lexiflow.main.argparse.ArgumentParser.parse_args")
def test_main_tui(mock_parse_args, mock_tui_main, mock_cli_main):
    # Case 3: 'tui' command provided -> run TUI
    mock_args = MagicMock()
    mock_args.command = "tui"
    mock_args.func = mock_tui_main
    mock_parse_args.return_value = mock_args

    main()
    mock_tui_main.assert_called_once()
    mock_cli_main.assert_not_called()


@patch("lexiflow.main.sys.exit")
@patch("lexiflow.main.argparse.ArgumentParser.parse_args")
def test_main_invalid_command(mock_parse_args, mock_sys_exit):
    # Case 4: Invalid command handling (usually handled by argparse itself,
    # but the else block handles cases where func is missing and command is not None)

    # Mock parse_args return value
    mock_args = MagicMock()
    # Ensure 'func' is NOT present
    del mock_args.func
    # Set command to something not None, but func is missing
    mock_args.command = "invalid"

    mock_parse_args.return_value = mock_args

    # Mock ArgumentParser constructor to capture instance
    with patch("lexiflow.main.argparse.ArgumentParser") as mock_argparser:
        mock_parser_instance = mock_argparser.return_value
        mock_parser_instance.parse_args.return_value = mock_args

        main()

        mock_parser_instance.print_help.assert_called_once()
        mock_sys_exit.assert_called_once_with(1)
