from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexiflow.input_handler import CLIInputHandler
from lexiflow.models import Config


@pytest.fixture
def mock_config():
    config = MagicMock(spec=Config)
    config.date_format = "%Y-%m-%d"
    return config


@pytest.fixture
def mock_show_clients():
    return MagicMock()


@pytest.fixture
def input_handler(mock_config, mock_show_clients):
    return CLIInputHandler(mock_config, mock_show_clients)


@pytest.fixture
def mock_args():
    args = MagicMock()
    # Initialize attributes with None
    args.client_id = None
    args.job_number = None
    args.date_received = None
    args.date_due = None
    args.work_on_file = None
    args.job_type = None
    args.quantity = None
    args.job_template = None
    args.note = None
    args.name = None
    args.email = None
    args.file = None
    return args


class TestGetJobInfo:
    def test_all_args_provided(self, input_handler, mock_args):
        """Test when all job info is provided in args"""
        mock_args.client_id = 1
        mock_args.job_number = "JOB123"
        mock_args.date_received = "2023-01-01"
        mock_args.date_due = "2023-01-10"

        job_file = Path("test_job.mp3")

        info = input_handler.get_job_info(mock_args, job_file)

        assert info["client_id"] == 1
        assert info["job_number"] == "JOB123"
        assert info["date_received"] == "2023-01-01"
        assert info["date_due"] == "2023-01-10"
        # Verify show_clients was not called
        input_handler.show_clients_func.assert_not_called()

    @patch("lexiflow.input_handler.prompt")
    @patch("lexiflow.input_handler.extract_job_number")
    @patch("lexiflow.input_handler.extract_date_due")
    def test_no_args_provided(
        self,
        mock_extract_due,
        mock_extract_job,
        mock_prompt,
        input_handler,
        mock_args,
    ):
        """Test when no info is provided in args, relying on prompts and extraction"""
        job_file = Path("test_job_123_due_01.10.mp3")

        # Mock extractions
        mock_extract_job.return_value = "JOB123"
        mock_extract_due.return_value = "01.10"

        # Mock prompt inputs: client_id, date_received, date_due
        # Note: job_number is extracted so prompt might be skipped for it depending on logic
        # Looking at code: if not job_number: job_number = extracted or prompt.
        # So if extracted returns value, prompt won't be called for job_number?
        # Wait, `or` evaluates both? No, short circuit.
        # `extract_job_number(...) or prompt(...)`
        # If extraction succeeds, prompt is NOT called for job number.

        # Prompts expected:
        # 1. client_id
        # 2. date_received
        # 3. date_due (default populated from extract_date_due)

        mock_prompt.side_effect = [
            "1",  # client_id
            # job_number extracted, no prompt
            "2023-01-01",  # date_received
            "2023-01-10",  # date_due
        ]

        info = input_handler.get_job_info(mock_args, job_file)

        assert info["client_id"] == 1
        assert info["job_number"] == "JOB123"
        assert info["date_received"] == "2023-01-01"
        assert info["date_due"] == "2023-01-10"

        input_handler.show_clients_func.assert_called_once()


class TestGetTaskInfo:
    @patch("lexiflow.input_handler.get_media_duration")
    def test_all_args_provided(self, mock_duration, input_handler, mock_args):
        """Test when all task info is provided in args"""
        mock_args.work_on_file = "y"
        mock_args.job_type = "Normal"
        mock_args.quantity = "60"
        mock_args.job_template = "zd"
        mock_args.note = "test note"

        mock_duration.return_value = 60.0
        task_file = Path("test.mp3")

        info = input_handler.get_task_info(mock_args, task_file)

        assert info["work_on_file"] == "y"
        assert info["job_type"] == "normal"  # converted to lower
        assert info["quantity"] == "60"
        assert info["total_quantity"] == 60.0
        assert info["job_template"] == "zd"
        assert info["note"] == "test note"

    @patch("lexiflow.input_handler.get_media_duration")
    @patch("lexiflow.input_handler.prompt")
    def test_prompts_needed(
        self, mock_prompt, mock_duration, input_handler, mock_args
    ):
        """Test prompts when args are missing"""
        mock_duration.return_value = 60.0
        task_file = Path("test.mp3")

        # Prompts: work_on_file, job_type, quantity, job_template, note
        mock_prompt.side_effect = ["y", "Normal", "60", "zd", "test note"]

        info = input_handler.get_task_info(mock_args, task_file)

        assert info["work_on_file"] == "y"
        assert info["job_type"] == "normal"
        assert info["quantity"] == "60"

    @patch("lexiflow.input_handler.prompt")
    def test_skip_file(self, mock_prompt, input_handler, mock_args):
        """Test skipping file when work_on_file is 'n'"""
        mock_prompt.return_value = "n"
        task_file = Path("test.mp3")

        info = input_handler.get_task_info(mock_args, task_file)
        assert info is None


class TestGetClientInfo:
    def test_args_provided(self, input_handler, mock_args):
        mock_args.name = "Test Client"
        mock_args.email = "test@example.com"

        info = input_handler.get_client_info(mock_args)
        assert info["name"] == "Test Client"
        assert info["email"] == "test@example.com"

    @patch("lexiflow.input_handler.prompt")
    def test_prompts(self, mock_prompt, input_handler, mock_args):
        mock_prompt.side_effect = ["Test Client", "test@example.com"]
        info = input_handler.get_client_info(mock_args)
        assert info["name"] == "Test Client"
        assert info["email"] == "test@example.com"


class TestGetFiles:
    def test_get_cutoff_file_arg(self, input_handler, mock_args):
        mock_args.file = "cutoffs.docx"
        path = input_handler.get_cutoff_file(mock_args)
        assert path == Path("cutoffs.docx")

    @patch("lexiflow.input_handler.prompt")
    def test_get_cutoff_file_prompt(
        self, mock_prompt, input_handler, mock_args
    ):
        mock_prompt.return_value = "cutoffs.docx"
        path = input_handler.get_cutoff_file(mock_args)
        assert path == Path("cutoffs.docx")

    def test_get_job_file_path_arg(self, input_handler, mock_args):
        mock_args.file = "job.mp3"
        path = input_handler.get_job_file_path(mock_args)
        assert path == Path("job.mp3")

    @patch("lexiflow.input_handler.prompt")
    def test_get_job_file_path_prompt(
        self, mock_prompt, input_handler, mock_args
    ):
        mock_prompt.return_value = "job.mp3"
        path = input_handler.get_job_file_path(mock_args)
        assert path == Path("job.mp3")
