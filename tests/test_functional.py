import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from lexiflow.base import Transcriptor
from lexiflow.cli import TranscriptorCMD
from lexiflow.models import Config


@pytest.fixture
def temp_workspace(tmp_path):
    """Sets up a temporary workspace for the functional tests."""
    workspace = tmp_path / "functional_test_workspace"
    workspace.mkdir()
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def app_config(temp_workspace):
    """Creates a configuration pointing to the temporary workspace."""
    return Config(
        base_dir=str(temp_workspace),
        date_format="%Y-%m-%d",
        invoice_theme="default",
    )


@pytest.fixture
def cli_app(app_config, temp_workspace):
    """
    Creates a TranscriptorCMD instance with a real Transcriptor backend
    but pointing to the temporary workspace.
    """
    # Initialize real Transcriptor with the test config
    # Pass a temporary config_file to avoid overwriting the user's global config
    test_config_file = temp_workspace / "config.yaml"
    app = Transcriptor(config=app_config, config_file=test_config_file)

    # Initialize CLI wrapper
    # Disable history and alias loading to avoid side effects
    cmd = TranscriptorCMD(app=app, history=False, alias=False)
    return cmd


@pytest.fixture
def dummy_audio_file(temp_workspace):
    """Creates a dummy mp3 file for job testing."""
    audio_file = temp_workspace / "test_audio.mp3"
    audio_file.touch()
    return audio_file


class TestFunctionalClientFlow:
    def test_add_and_show_client(self, cli_app):
        """
        Functional test:
        1. Add a new client via CLI args.
        2. Verify client exists in database.
        3. Verify client directory structure is created.
        """
        client_name = "Functional Client"
        client_email = "func@test.com"

        # 1. Add Client
        # Using onecmd to simulate CLI input
        cli_app.onecmd(f"add client -n '{client_name}' -e '{client_email}'")

        # 2. Verify Database
        clients = cli_app.app.api.get_clients(
            conditions={"name": [("=", client_name)]}
        )
        assert len(clients) == 1
        assert clients[0]["email"] == client_email

        # 3. Verify Filesystem
        client_dir = (
            Path(cli_app.app.config.base_dir)
            / "clients"
            / "Functional_Client"
        )
        assert client_dir.exists()
        assert (client_dir / "templates").exists()

    @patch("lexiflow.cli.prompt")
    def test_delete_client_interactive(self, mock_prompt, cli_app):
        """
        Functional test:
        1. Add a client.
        2. Delete the client interactively.
        3. Verify client is removed.
        """
        # Setup: Add client
        cli_app.app.create_client("Delete_Me", "del@test.com")

        # Mock user confirmation 'y' and then typing the client name
        mock_prompt.side_effect = ["y", "Delete_Me"]

        # Run delete command
        cli_app.onecmd("delete clients -w name=Delete_Me")

        # Verify removal
        clients = cli_app.app.api.get_clients(
            conditions={"name": [("=", "Delete_Me")]}
        )
        assert len(clients) == 0


class TestFunctionalJobFlow:
    @patch("lexiflow.input_handler.get_media_duration")
    def test_add_job_flow(self, mock_duration, cli_app, dummy_audio_file):
        """
        Functional test:
        1. Add a client.
        2. Add a job for that client.
        3. Verify job created in DB and files moved.
        """
        # Setup
        mock_duration.return_value = 10.0  # 10 minutes
        client_name = "Job Client"
        cli_app.app.create_client(client_name, "job@test.com")
        client = cli_app.app.api.get_clients(
            conditions={"name": [("=", client_name)]}
        )[0]
        client_id = client["id"]

        # Prepare arguments for add job
        # We simulate passing all required args to avoid interactive prompts
        cmd = (
            f"add job "
            f"-f {str(dummy_audio_file)} "
            f"-c {client_id} "
            f"-j JOB001 "
            f"-r 2023-10-01 "
            f"-d 2023-10-05 "
            f"-w y "
            f"-t Normal "
            f"-q 10 "
            f"-T zd "
            f"-N 'Test Note'"
        )

        cli_app.onecmd(cmd)

        # Verify Job in DB
        jobs = cli_app.app.api.get_jobs(
            conditions={"job_number": [("=", "JOB001")]}
        )
        assert len(jobs) == 1
        job = jobs[0]
        assert job["client_id"] == client_id
        assert job["amount"] == 4.0  # 10 * 0.4 (Normal rate)

        # Verify File Movement
        # The original dummy file should be moved/copied to the client directory
        # The logic in Transcriptor.create_job -> create_job_dir -> mv_extract_job_file
        # checks if file exists.

        # Verify job directory existence
        # Structure: clients/{client}/YYYY/Month/DD_Day_JOB_DUE_DD_Day
        # 2023-10-01 is Sunday (Sun), 2023-10-05 is Thursday (Thu)
        # However, checking exact path structure might be brittle if date utils change.
        # We can check via the job_path in DB.

        saved_job_path = Path(job["job_path"])
        assert saved_job_path.exists()
        assert saved_job_path.name.endswith(
            ".mp3"
        )  # Assuming dummy file extension
        assert client_name.replace(" ", "_") in str(saved_job_path)

    def test_update_job_status(self, cli_app):
        """
        Functional test:
        1. Create job manually (via API for speed).
        2. Update status via CLI.
        3. Verify status change.
        """
        # Setup
        cli_app.app.create_client("Update Client", "up@test.com")
        client_id = cli_app.app.api.get_clients()[0]["id"]

        job_data = {
            "client_id": client_id,
            "date_received": "2023-01-01",
            "job_number": "UP001",
            "job_type": "Normal",
            "status": "Pending",
            "date_due": "2023-01-10",
            "total_quantity": 10.0,
            "quantity": 10.0,
            "job_rate": 0.4,
            "amount": 4.0,
            "amount_paid": 0.0,
            "job_path": "/tmp/fake/path",
            "note": "To Update",
        }
        job_id = cli_app.app.api.add_job(job_data)

        # Update via CLI
        # update jobs -w id={job_id} -v status=Done
        cli_app.onecmd(f"update jobs -w id={job_id} -v status=Done")

        # Verify
        updated_job = cli_app.app.api.get_jobs(
            conditions={"id": [("=", job_id)]}
        )[0]
        assert updated_job["status"] == "Done"
        assert (
            updated_job["date_submitted"] is not None
        )  # Trigger should set this


class TestFunctionalInvoiceFlow:
    @patch("lexiflow.base.htmlstr_to_pdf")
    def test_generate_invoice_pdf(self, mock_pdf_gen, cli_app):
        """
        Functional test:
        1. Setup client and a 'Done' job (unpaid).
        2. Run invoice command.
        3. Verify PDF generator was called.
        4. Verify invoice counter incremented.
        """
        # Setup
        client_name = "Invoice Client"
        cli_app.app.create_client(client_name, "inv@test.com")
        client_id = cli_app.app.api.get_clients()[0]["id"]

        job_data = {
            "client_id": client_id,
            "date_received": "2023-01-01",
            "job_number": "INV001",
            "job_type": "Normal",
            "status": "Done",
            "date_due": "2023-01-10",
            "total_quantity": 100.0,
            "quantity": 100.0,
            "job_rate": 0.4,
            "amount": 40.0,
            "amount_paid": 0.0,  # Unpaid
            "job_path": "/tmp/fake/path",
            "date_submitted": "2023-01-05",  # Needs to be submitted
        }
        cli_app.app.api.add_job(job_data)

        # Run invoice command with -p (print/generate PDF)
        # invoice -c {id} -p
        # We also need to specify a condition or it might fail if logic requires it,
        # but get_invoice_jobs usually defaults to unpaid if basic conditions met.
        # The CLI 'invoice' command requires conditions OR summary flag.
        # Let's use a condition that is always true for this job.

        cli_app.onecmd(f"invoice -c {client_id} -w status=Done -p")

        # Verify PDF generation
        assert mock_pdf_gen.called

        # Verify invoice counter file
        client_dir = (
            Path(cli_app.app.config.base_dir) / "clients" / "Invoice_Client"
        )
        counter_file = client_dir / "invoices" / "invoice_number_counter"
        assert counter_file.exists()
        with open(counter_file, "r") as f:
            content = f.read().strip()
            # Should be 00001 after first invoice (or incremented logic)
            # The code initializes to 1 if not found, then increments?
            # let's check Transcriptor.increase_invoice_counter logic:
            # if not found: writes '00001'.
            # if found: reads, increments, writes.
            # So first run should result in '00001' written?
            # Wait, increase_invoice_counter logic:
            # FileNotFoundError -> write "00001"
            # Read -> current + 1 -> write.
            # However, generate_invoice calls `increase_invoice_counter`.
            # If it runs once, file created as '00001'?
            # Let's check Transcriptor.generate_invoice:
            # `invoice_number = self.read_invoice_counter(...)` -> returns 0 if not found
            # `Invoice(..., invoice_number=f"{invoice_number + 1:05}", ...)` -> Invoice obj gets '00001'
            # `self.increase_invoice_counter(...)` -> updates file to '00001'

        assert int(content) == 1


class TestFunctionalQueryComparison:
    @patch("lexiflow.cli.TranscriptorView.print_table")
    def test_compare_show_clients_cli(self, mock_print, cli_app):
        """
        Functional test: Compare 'show clients -w' vs 'show clients --raw'.
        """
        # Setup data
        cli_app.app.create_client("CLI_Compare", "cli@test.com")

        # 1. Command with -w
        cli_app.onecmd("show clients -w name=CLI_Compare")
        assert mock_print.called
        args_w, _ = mock_print.call_args
        data_w = args_w[0]
        mock_print.reset_mock()

        # 2. Command with --raw
        # Note: Depending on shell parsing in onecmd/cmd2, quotes might be tricky.
        # We assume cmd2 parses the string.
        # We need to ensure the raw SQL string is passed correctly.
        cli_app.onecmd("show clients --raw \"WHERE name = 'CLI_Compare'\"")
        assert mock_print.called
        args_raw, _ = mock_print.call_args
        data_raw = args_raw[0]

        # Assert Equality
        # data_w and data_raw should be lists of dicts
        assert len(data_w) == 1
        assert len(data_raw) == 1
        assert data_w == data_raw

    @patch("lexiflow.cli.TranscriptorView.print_table")
    @patch("lexiflow.input_handler.get_media_duration")
    def test_compare_show_jobs_cli(
        self, mock_duration, mock_print, cli_app, dummy_audio_file
    ):
        """
        Functional test: Compare 'show jobs -w' vs 'show jobs --raw'.
        """
        mock_duration.return_value = 10.0
        # Setup data
        cli_app.app.create_client("Job_Compare", "jc@test.com")
        client = cli_app.app.api.get_clients(
            conditions={"name": [("=", "Job_Compare")]}
        )[0]

        # Add a job
        cmd = (
            f"add job "
            f"-f {str(dummy_audio_file)} "
            f"-c {client['id']} "
            f"-j COMP001 "
            f"-r 2023-10-01 "
            f"-d 2023-10-05 "
            f"-w y "
            f"-t Normal "
            f"-q 10 "
            f"-T zd "
            f"-N 'Comparison Note'"
        )
        cli_app.onecmd(cmd)

        # 1. Command with -w
        cli_app.onecmd("show jobs -w job_number=COMP001")
        assert mock_print.called
        args_w, _ = mock_print.call_args
        data_w = args_w[0]
        mock_print.reset_mock()

        # 2. Command with --raw
        cli_app.onecmd("show jobs --raw \"WHERE job_number = 'COMP001'\"")
        assert mock_print.called
        args_raw, _ = mock_print.call_args
        data_raw = args_raw[0]

        # Assert Equality
        assert len(data_w) == 1
        assert len(data_raw) == 1

        # Check specific fields to ensure they match
        assert data_w[0]["job_number"] == data_raw[0]["job_number"]
        assert data_w[0]["amount"] == data_raw[0]["amount"]

        # Full equality might be tricky if one returns SQLAlchemy objects vs dicts slightly differently
        # in some edge cases, but for show_jobs they should be identical lists of dicts (or similar objects).
        # Based on api code, both return list of dicts.
        for j_w, j_raw in zip(data_w, data_raw):
            # Compare all keys except 'client'
            w_keys = {k: v for k, v in j_w.items() if k != "client"}
            # Raw SQL includes joined columns 'client_name' and 'client_email' which ORM dict doesn't
            raw_keys = {
                k: v
                for k, v in j_raw.items()
                if k not in ("client", "client_name", "client_email")
            }
            assert w_keys == raw_keys

            # Compare client objects
            if "client" in j_w and "client" in j_raw:
                assert j_w["client"].id == j_raw["client"].id
                assert j_w["client"].name == j_raw["client"].name
                assert j_w["client"].email == j_raw["client"].email
