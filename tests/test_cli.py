import json
import shutil
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexiflow.api import API
from lexiflow.cli import TranscriptorCMD
from lexiflow.models import Config, Profile

# Constants for testing
TEST_BASE_DIR = Path(__file__).parent / "test_cli_data"
CONFIG_FILE = TEST_BASE_DIR / "config.yaml"
PROFILE_FILE = TEST_BASE_DIR / "profile.yaml"
HISTORY_FILE = TEST_BASE_DIR / ".history"


@pytest.fixture(scope="module")
def test_base_dir():
    # Setup
    test_dir = TEST_BASE_DIR
    test_dir.mkdir(exist_ok=True)
    yield test_dir
    # Teardown
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def mock_transcriptor(test_base_dir):
    # Create a mock Transcriptor instance
    config = Config(
        base_dir=str(test_base_dir),
        date_format="%Y-%m-%d",
        invoice_theme="default",
    )
    profile = Profile()

    with patch("lexiflow.cli.Transcriptor", autospec=True) as mock:
        mock.return_value.config = config
        mock.return_value.profile = profile
        mock.return_value.base_dir = test_base_dir
        mock.return_value.CONFIG_DIR = test_base_dir
        mock.return_value.api = MagicMock(spec=API)
        mock.return_value.backup = MagicMock()  # Add backup mock
        yield mock


@pytest.fixture
def cli_app(mock_transcriptor, test_base_dir):
    # Mock the persistent history file operations
    app = TranscriptorCMD(
        history=False, alias=True
    )  # Disable history for tests
    yield app

    # Clean up after test
    if hasattr(app, "app"):
        del app.app


def test_cli_initialization(cli_app, mock_transcriptor):
    """Test CLI application initialization"""
    assert isinstance(cli_app, TranscriptorCMD)
    mock_transcriptor.assert_called_once()
    assert hasattr(cli_app, "app")
    assert cli_app.debug is True


def test_do_show_config(cli_app, mock_transcriptor):
    """Test 'show config' command"""
    # Mock the view's print_table method
    with patch("lexiflow.cli.TranscriptorView.print_table") as mock_print:
        result = cli_app.onecmd("show config")
        assert result is False
        mock_print.assert_called_once_with(
            mock_transcriptor.return_value.config.__dict__,
            title="Configuration",
        )


def test_do_show_profile(cli_app, mock_transcriptor):
    """Test 'show profile' command"""
    with patch("lexiflow.cli.TranscriptorView.print_table") as mock_print:
        result = cli_app.onecmd("show profile")
        assert result is False
        mock_print.assert_called_once_with(
            mock_transcriptor.return_value.profile.__dict__, title="Profile"
        )


def test_do_show_clients(cli_app, mock_transcriptor):
    """Test 'show clients' command"""
    mock_clients = [
        {"id": 1, "name": "Test Client", "email": "test@example.com"}
    ]
    mock_transcriptor.return_value.api.get_clients.return_value = mock_clients

    with patch("lexiflow.cli.TranscriptorView.print_table") as mock_print:
        result = cli_app.onecmd("show clients")
        assert result is False
        mock_print.assert_called_once_with(
            mock_clients, orientation="horizontal", title="Clients"
        )


def test_do_show_clients_with_conditions(cli_app, mock_transcriptor):
    """Test 'show clients' with conditions"""
    mock_transcriptor.return_value.api.get_clients.return_value = []

    with patch("lexiflow.cli.parse_conditions") as mock_parse:
        mock_parse.return_value = {"name": [("=", "Test")]}
        cli_app.onecmd("show clients -w name=Test")
        mock_transcriptor.return_value.api.get_clients.assert_called_once_with(
            conditions={"name": [("=", "Test")]}
        )


def test_do_add_client(cli_app, mock_transcriptor):
    """Test 'add client' command"""
    # Mock user input
    with patch(
        "lexiflow.cli.prompt",
        side_effect=["Test Client", "test@example.com"],
    ):
        result = cli_app.onecmd(
            "add client -n 'Test Client' -e 'test@example.com'"
        )
        assert result is False
        cli_app.app.create_client.assert_called_once()


def test_do_add_job(cli_app, mock_transcriptor):
    """Test 'add job' command"""
    # Setup mocks
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.name = "Test Client"
    mock_client.email = "test@example.com"

    cli_app.app.api.get_clients.return_value = [mock_client]

    # Mock file operations
    mock_file = MagicMock()
    mock_file.name = "test_file.mp3"

    # Mock input handler file path and info methods
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    cli_app.input_handler.get_job_file_path = MagicMock(
        return_value=mock_path
    )
    cli_app.input_handler.get_job_info = MagicMock(
        return_value={
            "client_id": 1,
            "job_number": "JOB001",
            "date_received": "2023-01-01",
            "date_due": "2023-01-10",
        }
    )
    cli_app.input_handler.get_task_info = MagicMock(
        return_value={
            "job_template": "zd",
            "job_type": "Normal",
            "quantity": "60",
            "note": "Cannot be late",
            "total_quantity": 60,
        }
    )

    # Mock user input
    input_sequence = {
        "client_id": "1",
        "job_number": "JOB001",
        "date_received": "2023-01-01",
        "date_due": "2023-01-10",
        "work_on_file": "y",
        "job_type": "Normal",
        "quantity": "60",
        "job_template": "zd",
        "note": "'Cannot be late'",
    }

    with patch("lexiflow.cli.prompt", side_effect=input_sequence):
        command = "add job -f test_file.mp3 -c {} -j {} -r {} -d {} -w {} -t {} -q {} -T {} -N {}".format(
            *[v for k, v in input_sequence.items()]
        )
        result = cli_app.onecmd(command)
        assert result is False
        cli_app.app.create_job.assert_called_once()


def test_do_update_config(cli_app, mock_transcriptor):
    """Test 'update config' command"""
    result = cli_app.onecmd("update config --date-format %d-%m-%Y")
    assert result is False
    assert mock_transcriptor.return_value.config.date_format == "%d-%m-%Y"
    mock_transcriptor.return_value.save_config.assert_called_once()


def test_do_update_profile(cli_app, mock_transcriptor):
    """Test 'update profile' command"""
    result = cli_app.onecmd("update profile --name 'Test User'")
    assert result is False
    assert mock_transcriptor.return_value.profile.name == "Test User"
    mock_transcriptor.return_value.save_profile.assert_called_once()


def test_do_delete_clients(cli_app, mock_transcriptor):
    """Test 'delete clients' command"""
    mock_transcriptor.return_value.api.get_clients.return_value = [
        {"id": 1, "name": "Test Client"}
    ]

    with patch("lexiflow.cli.prompt", side_effect=["y", "Test Client"]):
        result = cli_app.onecmd("delete clients -w name=Test")
        assert result is False
        mock_transcriptor.return_value.delete_clients.assert_called_once()


def test_do_invoice(cli_app, mock_transcriptor):
    """Test 'invoice' command"""
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.name = "Test Client"

    cli_app.app.api.get_clients.return_value = [mock_client]
    cli_app.app.get_invoice_jobs.return_value = []
    cli_app.app.generate_invoice.return_value = (
        "<html>Test</html>",
        "Test Client",
    )

    with patch("lexiflow.cli.prompt", return_value="1"):
        result = cli_app.onecmd("invoice -c 1 -w client_id=1")
        assert result is False
        cli_app.app.generate_invoice.assert_called_once()


def test_do_invoice_summary(cli_app, mock_transcriptor):
    """Test summary invoice generation"""
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.name = "Test Client"

    cli_app.app.api.get_clients.return_value = [mock_client]
    # Return a dict to emulate summary invoice structure
    cli_app.app.get_summary_invoice_jobs.return_value = {"Test Client": []}
    cli_app.app.generate_summary_invoice.return_value = (
        "<html>Summary</html>",
        "Test Client",
    )

    with patch("lexiflow.cli.prompt", return_value="1"):
        result = cli_app.onecmd("invoice -c 1 -S")
        assert result is False
        cli_app.app.generate_summary_invoice.assert_called_once()


def test_do_purge(cli_app, mock_transcriptor):
    """Test 'purge' command"""
    mock_jobs = [{"id": 1, "job_path": "test/path"}]
    mock_transcriptor.return_value.api.get_jobs.return_value = mock_jobs

    with patch("lexiflow.cli.prompt", return_value="y"):
        result = cli_app.onecmd("purge -w id=1")
        assert result is False
        mock_transcriptor.return_value.purge_job_files.assert_called_once_with(
            mock_jobs
        )


def test_do_exit(cli_app):
    """Test exit command"""
    with patch("lexiflow.cli.TranscriptorCMD.poutput"):
        result = cli_app.onecmd("exit")
        assert result is True


def test_do_quit(cli_app):
    """Test quit command"""
    with patch("lexiflow.cli.TranscriptorCMD.poutput"):
        result = cli_app.onecmd("quit")
        assert result is True


def test_do_EOF(cli_app):
    """Test EOF command"""
    with patch("lexiflow.cli.TranscriptorCMD.poutput"):
        result = cli_app.onecmd("EOF")
        assert result is True


def test_emptyline(cli_app):
    """Test empty line input"""
    result = cli_app.emptyline()
    assert result is None


def test_do_clear(cli_app):
    """Test clear command"""
    with patch("lexiflow.cli.os.system") as mock_system:
        result = cli_app.onecmd("clear")
        assert result is False
        mock_system.assert_called_once_with("clear")


def test_do_update_clients_missing_args(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.onecmd("update client")
    cli_app.poutput.assert_called_with("Please provide conditions and values")


def test_do_update_rates_missing_args(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.onecmd("update rates")
    cli_app.poutput.assert_called_with("Please provide conditions and values")


def test_do_update_jobs_missing_args(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.onecmd("update jobs")
    cli_app.poutput.assert_called_with("Please provide conditions and values")


def test_do_update_jobs_raw(cli_app, mock_transcriptor):
    cli_app.onecmd("update jobs --raw \"SET status='Done' WHERE id=1\"")
    mock_transcriptor.return_value.update_jobs.assert_called()


def test_do_backup(cli_app, mock_transcriptor):
    cli_app.onecmd("backup")
    mock_transcriptor.return_value.backup.create_backup.assert_called_once()


def test_do_restore(cli_app, mock_transcriptor):
    mock_backup = MagicMock()
    mock_backup.name = "backup.tar.gz"
    mock_transcriptor.return_value.backup.list_backups.return_value = [
        mock_backup
    ]

    with patch("lexiflow.cli.prompt", return_value="1"):
        cli_app.onecmd("restore")
        mock_transcriptor.return_value.backup.restore_backup.assert_called_with(
            mock_backup
        )


def test_do_restore_no_backups(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.backup.list_backups.return_value = []
    cli_app.poutput = MagicMock()
    cli_app.onecmd("restore")
    cli_app.poutput.assert_called_with("No backups found.")


def test_do_show_rates(cli_app, mock_transcriptor):
    cli_app.onecmd("show rates")
    mock_transcriptor.return_value.api.get_rates.assert_called_once()


def test_do_show_jobs(cli_app, mock_transcriptor):
    cli_app.onecmd("show jobs -a")
    mock_transcriptor.return_value.api.get_jobs.assert_called_with()


def test_do_show_jobs_pending(cli_app, mock_transcriptor):
    cli_app.onecmd("show jobs")
    mock_transcriptor.return_value.api.get_jobs.assert_called_with(
        conditions={"status": [("=", "Pending")]}
    )


def test_do_show_cutoffs(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.load_cutoffs.return_value = [
        ["2023-01-01", "2023-01-15"]
    ]
    cli_app.onecmd("show cutoffs")
    mock_transcriptor.return_value.load_cutoffs.assert_called_once()


def test_do_show_version(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.version = "1.0.0"
    cli_app.poutput = MagicMock()
    cli_app.onecmd("show version")
    cli_app.poutput.assert_called_with("Version: 1.0.0")


def test_do_add_cutoffs(cli_app, mock_transcriptor):
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True
    cli_app.input_handler.get_cutoff_file = MagicMock(return_value=mock_path)
    with patch(
        "lexiflow.cli.generate_cutoff_list_from_docx", return_value=[]
    ):
        cli_app.onecmd("add cutoffs -f test.docx")
        mock_transcriptor.return_value.save_cutoffs.assert_called_once()


def test_do_update_profile_full(cli_app, mock_transcriptor):
    cli_app.onecmd("update profile -n Name -a Area -c Country")
    assert mock_transcriptor.return_value.profile.name == "Name"
    assert mock_transcriptor.return_value.profile.area == "Area"
    assert mock_transcriptor.return_value.profile.country == "Country"
    mock_transcriptor.return_value.save_profile.assert_called_once()


def test_do_delete_jobs_no_confirm(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"job_number": "J1"}
    ]
    with patch("lexiflow.cli.prompt", return_value="y"):
        cli_app.onecmd("delete jobs -w id=1 -N")
        mock_transcriptor.return_value.delete_jobs.assert_called_once()


def test_do_invoice_no_args(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.onecmd("invoice")
    cli_app.poutput.assert_called()


def test_do_invoice_print(cli_app, mock_transcriptor):
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.name = "Client"
    mock_transcriptor.return_value.api.get_clients.return_value = [
        mock_client
    ]
    mock_transcriptor.return_value.generate_invoice.return_value = (
        "html",
        "Client",
    )

    cli_app.onecmd("invoice -c 1 -w id=1 -p")
    mock_transcriptor.return_value.html_to_pdf.assert_called_once()


def test_main_argv(mock_transcriptor):
    with patch("lexiflow.cli.TranscriptorCMD") as MockCMD:
        from lexiflow.cli import main

        main(["show", "version"])
        MockCMD.return_value.onecmd_plus_hooks.assert_called_with(
            "show version"
        )


def test_main_keyboard_interrupt(mock_transcriptor):
    with patch("lexiflow.cli.TranscriptorCMD") as MockCMD:
        MockCMD.return_value.cmdloop.side_effect = KeyboardInterrupt
        with patch("sys.exit"):
            from lexiflow.cli import main

            assert main() is True


def test_do_update_clients_raw(cli_app, mock_transcriptor):
    cli_app.onecmd("update client -r \"SET name='New' WHERE id=1\"")
    mock_transcriptor.return_value.api.update.assert_called_with(
        "clients", raw_sql_stmt="SET name='New' WHERE id=1"
    )


def test_do_update_job_table_no_values(cli_app):
    cli_app.poutput = MagicMock()
    with patch("lexiflow.cli.prompt", return_value="1"):
        cli_app.onecmd("update jobs -T")
        cli_app.poutput.assert_called_with(
            "Please provide values to be updated."
        )


def test_do_delete_clients_raw(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_clients.return_value = [
        {"name": "Test", "id": 1}
    ]
    # We need to mock prompt to return "y" then "Test" because the first prompt is "Are you sure..."?
    # No, delete_clients logic:
    # if args.no_confirm: ...
    # else: for client in clients: prompt("Are you sure...?") -> if y -> prompt("Type name to confirm")
    with patch("lexiflow.cli.prompt", side_effect=["y", "Test"]):
        cli_app.onecmd('delete clients -r "WHERE id=1"')
        mock_transcriptor.return_value.delete_clients.assert_called()


def test_do_delete_jobs_raw(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"job_number": "J1", "id": 1}
    ]
    with patch("lexiflow.cli.prompt", side_effect=["y", "J1"]):
        cli_app.onecmd('delete jobs -r "WHERE id=1"')
        mock_transcriptor.return_value.delete_jobs.assert_called()


def test_do_restore_invalid_input(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.backup.list_backups.return_value = [
        MagicMock(name="backup1")
    ]
    cli_app.poutput = MagicMock()
    with patch("lexiflow.cli.prompt", return_value="invalid"):
        cli_app.onecmd("restore")
        cli_app.poutput.assert_any_call(
            "Invalid input. Please enter a number."
        )


def test_do_restore_invalid_selection(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.backup.list_backups.return_value = [
        MagicMock(name="backup1")
    ]
    cli_app.poutput = MagicMock()
    with patch("lexiflow.cli.prompt", return_value="99"):
        cli_app.onecmd("restore")
        cli_app.poutput.assert_any_call("Invalid selection.")


def test_do_invoice_missing_args(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.onecmd("invoice")
    assert cli_app.poutput.called


def test_do_purge_raw(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"job_path": "path"}
    ]
    with patch("lexiflow.cli.prompt", return_value="y"):
        cli_app.onecmd('purge -r "WHERE id=1"')
        mock_transcriptor.return_value.purge_job_files.assert_called()


def test_do_add_job_file_not_found(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.input_handler.get_job_file_path = MagicMock(
        return_value=Path("non_existent")
    )
    cli_app.onecmd("add job -f non_existent")
    assert cli_app.poutput.called


def test_do_update_rates_where(cli_app, mock_transcriptor):
    with patch("lexiflow.cli.prompt", side_effect=["y"]):
        cli_app.onecmd("update rates -w id=1 -v normal=0.6")
        mock_transcriptor.return_value.api.update_rates.assert_called()


def test_do_update_job_raw(cli_app, mock_transcriptor):
    cli_app.onecmd("update jobs -r \"SET status='Done' WHERE id=1\"")
    mock_transcriptor.return_value.update_jobs.assert_called_with(
        raw_sql_stmt="SET status='Done' WHERE id=1"
    )


def test_do_delete_clients_confirm(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_clients.return_value = [
        {"name": "Test", "id": 1}
    ]
    # Prompt: Are you sure? (y), Type Test to confirm (Test)
    with patch("lexiflow.cli.prompt", side_effect=["y", "Test"]):
        cli_app.onecmd("delete clients -w id=1")
        mock_transcriptor.return_value.delete_clients.assert_called()


def test_do_invoice_raw(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.get_invoice_jobs.return_value = []
    mock_transcriptor.return_value.generate_invoice.return_value = (
        "html",
        "Client",
    )

    with patch("lexiflow.cli.prompt", return_value="1"):
        cli_app.onecmd('invoice -r "WHERE id=1"')
        mock_transcriptor.return_value.get_invoice_jobs.assert_called()


def test_do_invoice_table(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.load_cutoffs.return_value = [
        ["Cutoff", "Deposit"],
        ["2023-01-01", "2023-01-15"],
    ]
    mock_transcriptor.return_value.select_cutoff_period.return_value = (
        "2023-01-01",
        "2023-01-15",
    )
    mock_transcriptor.return_value.get_invoice_jobs.return_value = []
    mock_transcriptor.return_value.generate_invoice.return_value = (
        "html",
        "Client",
    )

    with patch(
        "lexiflow.cli.prompt", side_effect=["1", "1"]
    ):  # client_id, cutoff_idx
        cli_app.onecmd("invoice -T")
        mock_transcriptor.return_value.get_invoice_jobs.assert_called()


def test_do_add_client_missing(cli_app, mock_transcriptor):
    cli_app.poutput = MagicMock()
    cli_app.input_handler.get_client_info = MagicMock(
        return_value={"name": "", "email": ""}
    )
    cli_app.onecmd("add client")
    cli_app.poutput.assert_called_with("Name and email are required.")


def test_do_delete_clients_no_where(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.onecmd("delete clients")
    cli_app.poutput.assert_called_with("Please provide conditions to delete")


def test_do_delete_clients_not_found(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_clients.return_value = []
    cli_app.poutput = MagicMock()
    cli_app.onecmd("delete clients -w id=999")
    cli_app.poutput.assert_called_with("No clients found")


def test_do_invoice_csv(cli_app, mock_transcriptor):
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.name = "Client"
    mock_transcriptor.return_value.api.get_clients.return_value = [
        mock_client
    ]
    mock_transcriptor.return_value.get_invoice_jobs.return_value = []
    mock_transcriptor.return_value.generate_invoice.return_value = (
        "html",
        "Client",
    )

    cli_app.onecmd("invoice -c 1 -w id=1 --csv")
    mock_transcriptor.return_value.generate_csv_invoice.assert_called_once()


def test_do_invoice_markdown(cli_app, mock_transcriptor):
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.name = "Client"
    mock_transcriptor.return_value.api.get_clients.return_value = [
        mock_client
    ]
    mock_transcriptor.return_value.get_invoice_jobs.return_value = []
    mock_transcriptor.return_value.generate_invoice.return_value = (
        "html",
        "Client",
    )
    mock_transcriptor.return_value.to_md.return_value = "markdown"

    with patch("rich.console.Console.print") as mock_print:
        cli_app.onecmd("invoice -c 1 -w id=1 -m")
        mock_print.assert_called()


def test_do_purge_no_args(cli_app):
    cli_app.poutput = MagicMock()
    cli_app.onecmd("purge")
    cli_app.poutput.assert_called_with("Please provide conditions to purge")


def test_do_update_job_conditions_values(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_jobs.return_value = [{"id": 1}]
    cli_app.onecmd("update jobs -w id=1 -v status=Done")
    mock_transcriptor.return_value.update_jobs.assert_called()


def test_do_delete_clients_interactive(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_clients.return_value = [
        {"name": "Client1", "id": 1}
    ]
    # Prompt flow:
    # 1. Are you sure? (y)
    # 2. Type Client1 to confirm (Client1)
    with patch("lexiflow.cli.prompt", side_effect=["y", "Client1"]):
        cli_app.onecmd("delete clients -w id=1")
        mock_transcriptor.return_value.delete_clients.assert_called()


def test_do_invoice_prompt_client(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.get_invoice_jobs.return_value = []
    mock_transcriptor.return_value.generate_invoice.return_value = (
        "html",
        "Client",
    )

    # Prompt for client id
    with patch("lexiflow.cli.prompt", return_value="1"):
        cli_app.onecmd("invoice -w id=1")
        mock_transcriptor.return_value.get_invoice_jobs.assert_called()


# -------- transcribe submit/status/fetch --------


def test_do_transcribe_submit(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.submit_transcription.return_value = (
        "ext-123"
    )
    cli_app.poutput = MagicMock()

    cli_app.onecmd("transcribe submit -j 5 -P revai")

    mock_transcriptor.return_value.submit_transcription.assert_called_once_with(
        5, "revai", additional_vocabulary=None
    )
    cli_app.poutput.assert_called_with(
        "Submitted job 5 to revai: ext-123"
    )


def test_do_transcribe_submit_with_vocabulary(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.submit_transcription.return_value = "ext-1"

    cli_app.onecmd(
        "transcribe submit -j 5 -P speechmatics --vocabulary 'Plaintiff, Defendant'"
    )

    mock_transcriptor.return_value.submit_transcription.assert_called_once_with(
        5, "speechmatics", additional_vocabulary=["Plaintiff", "Defendant"]
    )


def test_do_transcribe_submit_error(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.submit_transcription.side_effect = (
        FileNotFoundError("Job file not found: /tmp/x.mp3")
    )
    cli_app.poutput = MagicMock()

    cli_app.onecmd("transcribe submit -j 5 -P revai")

    cli_app.poutput.assert_called_with(
        "Error: Job file not found: /tmp/x.mp3"
    )


def test_do_transcribe_submit_prompts_for_provider_when_omitted(
    cli_app, mock_transcriptor
):
    mock_transcriptor.return_value.submit_transcription.return_value = "ext-1"
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="2"):
        cli_app.onecmd("transcribe submit -j 5")

    mock_transcriptor.return_value.submit_transcription.assert_called_once_with(
        5, "revai", additional_vocabulary=None
    )


def test_do_transcribe_submit_invalid_provider_selection_stops(
    cli_app, mock_transcriptor
):
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="99"):
        cli_app.onecmd("transcribe submit -j 5")

    mock_transcriptor.return_value.submit_transcription.assert_not_called()
    cli_app.poutput.assert_called_with("Invalid selection.")


def test_do_open(cli_app, mock_transcriptor, tmp_path):
    mock_transcriptor.return_value.get_job_directory.return_value = tmp_path

    with patch("lexiflow.cli.open_in_file_manager") as mock_open:
        cli_app.onecmd("open -j 5")

    mock_transcriptor.return_value.get_job_directory.assert_called_once_with(
        5
    )
    mock_open.assert_called_once_with(tmp_path)


def test_do_open_invalid_job(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.get_job_directory.side_effect = (
        ValueError("Job 5 not found")
    )
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.open_in_file_manager") as mock_open:
        cli_app.onecmd("open -j 5")

    mock_open.assert_not_called()
    cli_app.poutput.assert_called_with("Error: Job 5 not found")


def test_do_transcribe_status(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.poll_transcription_status.return_value = (
        "transcribed"
    )
    cli_app.poutput = MagicMock()

    cli_app.onecmd("transcribe status -j 5")

    mock_transcriptor.return_value.poll_transcription_status.assert_called_once_with(
        5
    )
    cli_app.poutput.assert_called_with("Job 5 status: transcribed")


def test_do_transcribe_status_none(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.poll_transcription_status.return_value = (
        None
    )
    cli_app.poutput = MagicMock()

    cli_app.onecmd("transcribe status -j 5")

    cli_app.poutput.assert_called_with(
        "Job 5 has no transcription in progress, "
        "or the provider poll failed."
    )


def test_do_transcribe_fetch(cli_app, mock_transcriptor, tmp_path):
    transcript_path = tmp_path / "TX001_transcript.txt"
    mock_transcriptor.return_value.fetch_transcript.return_value = (
        transcript_path
    )
    cli_app.poutput = MagicMock()

    cli_app.onecmd("transcribe fetch -j 5")

    mock_transcriptor.return_value.fetch_transcript.assert_called_once_with(
        5, metadata=None
    )
    cli_app.poutput.assert_called_with(f"Transcript saved to {transcript_path}")


def test_do_transcribe_fetch_with_metadata(
    cli_app, mock_transcriptor, tmp_path
):
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text('{"WITNESS_NAME": "Jane Doe"}')
    mock_transcriptor.return_value.fetch_transcript.return_value = (
        tmp_path / "out.txt"
    )

    cli_app.onecmd(f"transcribe fetch -j 5 -m {metadata_file}")

    mock_transcriptor.return_value.fetch_transcript.assert_called_once_with(
        5, metadata={"WITNESS_NAME": "Jane Doe"}
    )


def test_do_transcribe_fetch_missing_metadata_file(cli_app, mock_transcriptor):
    cli_app.poutput = MagicMock()

    cli_app.onecmd("transcribe fetch -j 5 -m /nonexistent/metadata.json")

    cli_app.poutput.assert_called_with(
        "Metadata file not found: /nonexistent/metadata.json"
    )
    mock_transcriptor.return_value.fetch_transcript.assert_not_called()


def test_do_transcribe_no_subcommand(cli_app):
    cli_app.do_help = MagicMock()
    cli_app.onecmd("transcribe")
    cli_app.do_help.assert_called_with("transcribe")


def test_do_extract_writes_metadata_json(cli_app, tmp_path):
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    notice.write_bytes(b"%PDF-1.4 fake")
    pbs.write_bytes(b"%PDF-1.4 fake")
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {
            "WITNESS_NAME": "Jane Doe"
        }
        cli_app.onecmd(f"extract -n {notice} -p {pbs}")
        mock_extractor_cls.return_value.extract_all.assert_called_once_with(
            notice, pbs
        )

    output_path = tmp_path / "metadata.json"
    assert output_path.exists()
    assert json.loads(output_path.read_text()) == {"WITNESS_NAME": "Jane Doe"}
    cli_app.poutput.assert_called_with(f"Metadata saved to {output_path}")


def test_do_extract_explicit_output(cli_app, tmp_path):
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    notice.write_bytes(b"%PDF-1.4 fake")
    pbs.write_bytes(b"%PDF-1.4 fake")
    output = tmp_path / "custom" / "meta.json"

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {"A": "1"}
        cli_app.onecmd(f"extract -n {notice} -p {pbs} -o {output}")

    assert output.exists()
    assert json.loads(output.read_text()) == {"A": "1"}


def test_do_extract_error(cli_app, tmp_path):
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    notice.write_bytes(b"%PDF-1.4 fake")
    pbs.write_bytes(b"%PDF-1.4 fake")
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.side_effect = RuntimeError(
            "boom"
        )
        cli_app.onecmd(f"extract -n {notice} -p {pbs}")

    cli_app.poutput.assert_called_with("Error extracting metadata: boom")


def test_do_extract_interactive_via_job_id(cli_app, mock_transcriptor, tmp_path):
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    notice.touch()
    pbs.touch()
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(tmp_path / "audio.mp3")}
    ]
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {
            "WITNESS_NAME": "Jane Doe"
        }
        with patch("lexiflow.cli.prompt", side_effect=["1", "1"]):
            cli_app.onecmd("extract -j 739")

    mock_extractor_cls.return_value.extract_all.assert_called_once_with(
        notice, pbs
    )
    assert (tmp_path / "metadata.json").exists()


def test_do_extract_bare_prompts_for_job_id_first(
    cli_app, mock_transcriptor, tmp_path
):
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    notice.touch()
    pbs.touch()
    mock_transcriptor.return_value.get_job_directory.return_value = tmp_path
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(tmp_path / "audio.mp3")}
    ]

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {"A": "1"}
        with patch(
            "lexiflow.cli.prompt", side_effect=["739", "1", "1"]
        ):
            cli_app.onecmd("extract")

    mock_extractor_cls.return_value.extract_all.assert_called_once_with(
        notice, pbs
    )


def test_do_extract_interactive_notice_pick_cancelled_stops(
    cli_app, mock_transcriptor, tmp_path
):
    notice = tmp_path / "notice.pdf"
    notice.touch()
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(tmp_path / "audio.mp3")}
    ]

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        with patch("lexiflow.cli.prompt", return_value="abc"):
            cli_app.onecmd("extract -j 739")

    mock_extractor_cls.assert_not_called()


def test_do_fill_with_metadata_file(cli_app, tmp_path):
    template = tmp_path / "template.docx"
    template.write_bytes(b"fake docx")
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text('{"WITNESS_NAME": "Jane Doe"}')
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.fill_template") as mock_fill:
        mock_fill.return_value = tmp_path / "template_filled.docx"
        cli_app.onecmd(f"fill -t {template} -m {metadata_file}")

    mock_fill.assert_called_once_with(
        template, {"WITNESS_NAME": "Jane Doe"}, None
    )
    cli_app.poutput.assert_called_with(
        f"Filled template saved to {tmp_path / 'template_filled.docx'}"
    )


def test_do_fill_with_notice_and_pbs_extracts_first(cli_app, tmp_path):
    template = tmp_path / "template.docx"
    template.write_bytes(b"fake docx")
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    notice.write_bytes(b"%PDF-1.4 fake")
    pbs.write_bytes(b"%PDF-1.4 fake")

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {
            "WITNESS_NAME": "Jane Doe"
        }
        with patch("lexiflow.cli.fill_template") as mock_fill:
            mock_fill.return_value = tmp_path / "template_filled.docx"
            cli_app.onecmd(f"fill -t {template} -n {notice} -p {pbs}")

    mock_extractor_cls.return_value.extract_all.assert_called_once_with(
        notice, pbs
    )
    mock_fill.assert_called_once_with(
        template, {"WITNESS_NAME": "Jane Doe"}, None
    )
    # extract's own side effect (writing metadata.json) still happens
    assert (pbs.parent / "metadata.json").exists()


def test_do_fill_notice_without_pbs_errors(cli_app, tmp_path):
    template = tmp_path / "template.docx"
    template.write_bytes(b"fake docx")
    notice = tmp_path / "notice.pdf"
    notice.write_bytes(b"%PDF-1.4 fake")
    cli_app.poutput = MagicMock()

    cli_app.onecmd(f"fill -t {template} -n {notice}")

    cli_app.poutput.assert_called_with(
        "Error: -p/--pbs is required when using -n/--notice"
    )


def test_do_fill_missing_metadata_file(cli_app, tmp_path):
    template = tmp_path / "template.docx"
    template.write_bytes(b"fake docx")
    cli_app.poutput = MagicMock()

    cli_app.onecmd(f"fill -t {template} -m /nonexistent/metadata.json")

    cli_app.poutput.assert_called_with(
        "Metadata file not found: /nonexistent/metadata.json"
    )


def test_do_fill_error(cli_app, tmp_path):
    template = tmp_path / "template.docx"
    template.write_bytes(b"fake docx")
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text("{}")
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.fill_template") as mock_fill:
        mock_fill.side_effect = RuntimeError("boom")
        cli_app.onecmd(f"fill -t {template} -m {metadata_file}")

    cli_app.poutput.assert_called_with("Error filling template: boom")


def test_do_fill_interactive_picks_template_and_reuses_metadata_json(
    cli_app, mock_transcriptor, tmp_path
):
    template = tmp_path / "template.docx"
    template.touch()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text('{"WITNESS_NAME": "Jane Doe"}')
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(tmp_path / "audio.mp3")}
    ]

    with patch("lexiflow.cli.fill_template") as mock_fill:
        mock_fill.return_value = tmp_path / "template_filled.docx"
        with patch("lexiflow.cli.prompt", side_effect=["1", "y"]):
            cli_app.onecmd("fill -j 739")

    mock_fill.assert_called_once_with(
        template, {"WITNESS_NAME": "Jane Doe"}, None
    )


def test_do_fill_interactive_declines_reuse_picks_notice_and_pbs(
    cli_app, mock_transcriptor, tmp_path
):
    template = tmp_path / "template.docx"
    template.touch()
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    template.touch()
    notice.touch()
    pbs.touch()
    (tmp_path / "metadata.json").write_text("{}")
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(tmp_path / "audio.mp3")}
    ]

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {
            "WITNESS_NAME": "Jane Doe"
        }
        with patch("lexiflow.cli.fill_template") as mock_fill:
            mock_fill.return_value = tmp_path / "template_filled.docx"
            with patch(
                "lexiflow.cli.prompt", side_effect=["1", "n", "1", "1"]
            ):
                cli_app.onecmd("fill -j 739")

    mock_extractor_cls.return_value.extract_all.assert_called_once_with(
        notice, pbs
    )
    mock_fill.assert_called_once_with(
        template, {"WITNESS_NAME": "Jane Doe"}, None
    )


def test_do_fill_interactive_no_metadata_json_skips_reuse_prompt(
    cli_app, mock_transcriptor, tmp_path
):
    template = tmp_path / "template.docx"
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    template.touch()
    notice.touch()
    pbs.touch()
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(tmp_path / "audio.mp3")}
    ]

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {"A": "1"}
        with patch("lexiflow.cli.fill_template") as mock_fill:
            mock_fill.return_value = tmp_path / "template_filled.docx"
            with patch(
                "lexiflow.cli.prompt", side_effect=["1", "1", "1"]
            ):
                cli_app.onecmd("fill -j 739")

    mock_extractor_cls.return_value.extract_all.assert_called_once_with(
        notice, pbs
    )


def test_do_fill_bare_prompts_for_job_id_first(
    cli_app, mock_transcriptor, tmp_path
):
    template = tmp_path / "template.docx"
    template.touch()
    (tmp_path / "metadata.json").write_text("{}")
    mock_transcriptor.return_value.get_job_directory.return_value = tmp_path
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(tmp_path / "audio.mp3")}
    ]

    with patch("lexiflow.cli.fill_template") as mock_fill:
        mock_fill.return_value = tmp_path / "template_filled.docx"
        with patch(
            "lexiflow.cli.prompt", side_effect=["739", "1", "y"]
        ):
            cli_app.onecmd("fill")

    mock_fill.assert_called_once_with(template, {}, None)


def test_do_fill_no_template_and_no_job_context_errors(cli_app, tmp_path):
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text("{}")
    cli_app.poutput = MagicMock()

    cli_app.onecmd(f"fill -m {metadata_file}")

    cli_app.poutput.assert_called_with("Error: -t/--template is required")


def _process_paths(tmp_path):
    notice = tmp_path / "notice.pdf"
    pbs = tmp_path / "pbs.pdf"
    audio = tmp_path / "audio.mp3"
    notice.write_bytes(b"%PDF-1.4 fake")
    pbs.write_bytes(b"%PDF-1.4 fake")
    audio.write_bytes(b"fake audio")
    return notice, pbs, audio


def test_do_process_submits_without_wait(cli_app, tmp_path):
    notice, pbs, audio = _process_paths(tmp_path)
    cli_app.poutput = MagicMock()

    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-job-1"

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {
            "WITNESS_NAME": "Jane Doe"
        }
        with patch("lexiflow.cli.get_service", return_value=mock_service):
            cli_app.onecmd(
                f"process -n {notice} -p {pbs} -a {audio} -P revai"
            )

    mock_service.submit_job.assert_called_once()
    submit_args, submit_kwargs = mock_service.submit_job.call_args
    assert submit_args[0] == audio
    assert submit_kwargs["additional_vocabulary"] == ["Jane", "Doe"]
    mock_service.get_job_status.assert_not_called()
    mock_service.close.assert_awaited_once()
    assert (pbs.parent / "metadata.json").exists()
    cli_app.poutput.assert_any_call(f"Submitted {audio} to revai: ext-job-1")


def test_do_process_with_template_fills_it(cli_app, tmp_path):
    notice, pbs, audio = _process_paths(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"fake docx")

    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-job-1"

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {"A": "1"}
        with patch("lexiflow.cli.get_service", return_value=mock_service):
            with patch("lexiflow.cli.fill_template") as mock_fill:
                mock_fill.return_value = tmp_path / "template_filled.docx"
                cli_app.onecmd(
                    f"process -n {notice} -p {pbs} -a {audio} -P revai -t {template}"
                )

    mock_fill.assert_called_once_with(
        template, {"A": "1"}, tmp_path / "template_filled.docx"
    )


def test_do_process_wait_polls_until_transcribed(cli_app, tmp_path):
    notice, pbs, audio = _process_paths(tmp_path)
    cli_app.poutput = MagicMock()

    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-job-1"
    mock_service.get_job_status.return_value = {"status": "transcribed"}
    mock_service.get_transcript.return_value = "the transcript text"

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {}
        with patch("lexiflow.cli.get_service", return_value=mock_service):
            with patch("lexiflow.cli.asyncio.sleep", new=AsyncMock()):
                cli_app.onecmd(
                    f"process -n {notice} -p {pbs} -a {audio} -P revai --wait"
                )

    mock_service.get_transcript.assert_called_once_with("ext-job-1")
    output_txt = pbs.parent / "audio.txt"
    assert output_txt.exists()
    assert output_txt.read_text() == "the transcript text"


def test_do_process_wait_reports_failure(cli_app, tmp_path):
    notice, pbs, audio = _process_paths(tmp_path)
    cli_app.poutput = MagicMock()

    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-job-1"
    mock_service.get_job_status.return_value = {"status": "failed"}

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {}
        with patch("lexiflow.cli.get_service", return_value=mock_service):
            with patch("lexiflow.cli.asyncio.sleep", new=AsyncMock()):
                cli_app.onecmd(
                    f"process -n {notice} -p {pbs} -a {audio} -P revai --wait"
                )

    mock_service.get_transcript.assert_not_called()
    cli_app.poutput.assert_any_call("Transcription failed.")


def test_do_process_extract_error_stops_before_submit(cli_app, tmp_path):
    notice, pbs, audio = _process_paths(tmp_path)
    cli_app.poutput = MagicMock()

    mock_service = AsyncMock()

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.side_effect = RuntimeError(
            "boom"
        )
        with patch("lexiflow.cli.get_service", return_value=mock_service):
            cli_app.onecmd(
                f"process -n {notice} -p {pbs} -a {audio} -P revai"
            )

    mock_service.submit_job.assert_not_called()
    cli_app.poutput.assert_called_with("Error extracting metadata: boom")


def test_do_process_interactive_auto_fills_audio_picks_notice_and_pbs(
    cli_app, mock_transcriptor, tmp_path
):
    notice, pbs, audio = _process_paths(tmp_path)
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(audio)}
    ]

    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-job-1"

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {}
        with patch("lexiflow.cli.get_service", return_value=mock_service):
            with patch("lexiflow.cli.prompt", side_effect=["1", "1"]):
                cli_app.onecmd("process -j 739 -P revai")

    mock_extractor_cls.return_value.extract_all.assert_called_once_with(
        notice, pbs
    )
    mock_service.submit_job.assert_called_once()
    submit_args, _ = mock_service.submit_job.call_args
    assert submit_args[0] == audio


def test_do_process_interactive_missing_audio_file_errors(
    cli_app, mock_transcriptor, tmp_path
):
    notice, pbs, audio = _process_paths(tmp_path)
    audio.unlink()
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(audio)}
    ]
    cli_app.poutput = MagicMock()

    mock_service = AsyncMock()

    with patch("lexiflow.cli.get_service", return_value=mock_service):
        cli_app.onecmd("process -j 739 -P revai")

    cli_app.poutput.assert_called_with(f"Error: Job file not found: {audio}")
    mock_service.submit_job.assert_not_called()


def test_do_process_explicit_audio_skips_auto_fill(
    cli_app, mock_transcriptor, tmp_path
):
    notice, pbs, audio = _process_paths(tmp_path)
    other_audio = tmp_path / "other.mp3"
    other_audio.write_bytes(b"fake audio")
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 739, "job_path": str(audio)}
    ]

    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-job-1"

    with patch("lexiflow.cli.MetadataExtractor") as mock_extractor_cls:
        mock_extractor_cls.return_value.extract_all.return_value = {}
        with patch("lexiflow.cli.get_service", return_value=mock_service):
            cli_app.onecmd(
                f"process -j 739 -n {notice} -p {pbs} -a {other_audio} -P revai"
            )

    submit_args, _ = mock_service.submit_job.call_args
    assert submit_args[0] == other_audio


def test_prompt_pick_file_lists_and_returns_selection(cli_app, tmp_path):
    pdf1 = tmp_path / "a.pdf"
    pdf2 = tmp_path / "b.pdf"
    pdf1.touch()
    pdf2.touch()
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="2"):
        result = cli_app._prompt_pick_file(tmp_path, [".pdf"], "notice")

    assert result == pdf2
    cli_app.poutput.assert_any_call("Select notice:")
    cli_app.poutput.assert_any_call("1: a.pdf")
    cli_app.poutput.assert_any_call("2: b.pdf")


def test_prompt_pick_file_no_candidates(cli_app, tmp_path):
    cli_app.poutput = MagicMock()

    result = cli_app._prompt_pick_file(tmp_path, [".pdf"], "notice")

    assert result is None
    cli_app.poutput.assert_called_with(
        f"No notice candidates found in {tmp_path}"
    )


def test_prompt_pick_file_invalid_selection(cli_app, tmp_path):
    (tmp_path / "a.pdf").touch()
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="99"):
        result = cli_app._prompt_pick_file(tmp_path, [".pdf"], "notice")

    assert result is None
    cli_app.poutput.assert_called_with("Invalid selection.")


def test_prompt_pick_file_non_numeric_input(cli_app, tmp_path):
    (tmp_path / "a.pdf").touch()
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="abc"):
        result = cli_app._prompt_pick_file(tmp_path, [".pdf"], "notice")

    assert result is None
    cli_app.poutput.assert_called_with("Invalid input. Please enter a number.")


def test_prompt_pick_file_excludes_given_paths(cli_app, tmp_path):
    pdf1 = tmp_path / "a.pdf"
    pdf2 = tmp_path / "b.pdf"
    pdf1.touch()
    pdf2.touch()
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="1"):
        result = cli_app._prompt_pick_file(
            tmp_path, [".pdf"], "pbs", exclude={pdf1}
        )

    assert result == pdf2


def test_prompt_pick_job_id_valid(cli_app, mock_transcriptor, tmp_path):
    mock_transcriptor.return_value.get_job_directory.return_value = tmp_path

    with patch("lexiflow.cli.prompt", return_value="5"):
        result = cli_app._prompt_pick_job_id()

    assert result == 5
    mock_transcriptor.return_value.get_job_directory.assert_called_once_with(5)


def test_prompt_pick_job_id_not_found(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.get_job_directory.side_effect = ValueError(
        "No job found with id 999"
    )
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="999"):
        result = cli_app._prompt_pick_job_id()

    assert result is None
    cli_app.poutput.assert_called_with("Error: No job found with id 999")


def test_prompt_pick_job_id_non_numeric(cli_app):
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="abc"):
        result = cli_app._prompt_pick_job_id()

    assert result is None
    cli_app.poutput.assert_called_with("Invalid input. Please enter a number.")


def test_resolve_job_context_uses_explicit_job_id(cli_app, mock_transcriptor, tmp_path):
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 5, "job_path": str(tmp_path / "audio.mp3")}
    ]

    result = cli_app._resolve_job_context(Namespace(job_id=5))

    assert result == (
        {"id": 5, "job_path": str(tmp_path / "audio.mp3")},
        tmp_path,
    )
    mock_transcriptor.return_value.api.get_jobs.assert_called_once_with(
        conditions={"id": [("=", 5)]}
    )


def test_resolve_job_context_prompts_when_job_id_missing(
    cli_app, mock_transcriptor, tmp_path
):
    mock_transcriptor.return_value.get_job_directory.return_value = tmp_path
    mock_transcriptor.return_value.api.get_jobs.return_value = [
        {"id": 7, "job_path": str(tmp_path / "audio.mp3")}
    ]

    with patch("lexiflow.cli.prompt", return_value="7"):
        result = cli_app._resolve_job_context(Namespace(job_id=None))

    assert result == (
        {"id": 7, "job_path": str(tmp_path / "audio.mp3")},
        tmp_path,
    )


def test_resolve_job_context_missing_job_returns_none(cli_app, mock_transcriptor):
    mock_transcriptor.return_value.api.get_jobs.return_value = []
    cli_app.poutput = MagicMock()

    result = cli_app._resolve_job_context(Namespace(job_id=5))

    assert result is None
    cli_app.poutput.assert_called_with("Error: No job found with id 5")


def test_prompt_pick_provider_returns_selection(cli_app):
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="2"):
        result = cli_app._prompt_pick_provider()

    assert result == "revai"
    cli_app.poutput.assert_any_call("Select provider:")
    cli_app.poutput.assert_any_call("1: speechmatics")
    cli_app.poutput.assert_any_call("2: revai")
    cli_app.poutput.assert_any_call("3: notebooklm")


def test_prompt_pick_provider_invalid_selection(cli_app):
    cli_app.poutput = MagicMock()

    with patch("lexiflow.cli.prompt", return_value="99"):
        result = cli_app._prompt_pick_provider()

    assert result is None
    cli_app.poutput.assert_called_with("Invalid selection.")
