import asyncio
import shutil
import zipfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from lexiflow.api import API
from lexiflow.base import Transcriptor
from lexiflow.models import Config

# Constants for testing
TEST_BASE_DIR = Path(__file__).parent / "test_transcriptor_data"
CONFIG_FILE = TEST_BASE_DIR / "config.yaml"
PROFILE_FILE = TEST_BASE_DIR / "profile.yaml"


@pytest.fixture(scope="module")
def test_base_dir():
    # Setup
    test_dir = TEST_BASE_DIR
    test_dir.mkdir(exist_ok=True)
    yield test_dir
    # Teardown
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def clean_config(test_base_dir):
    # Ensure clean config for each test
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    yield
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


@pytest.fixture
def clean_profile(test_base_dir):
    # Ensure clean profile for each test
    if PROFILE_FILE.exists():
        PROFILE_FILE.unlink()
    yield
    if PROFILE_FILE.exists():
        PROFILE_FILE.unlink()


@pytest.fixture
def default_config():
    return {
        "base_dir": str(TEST_BASE_DIR),
        "date_format": "%Y-%m-%d",
        "invoice_theme": "default",
    }


@pytest.fixture
def default_profile():
    return {"name": "", "area": "", "country": ""}


@pytest.fixture
def transcriptor(test_base_dir, clean_config, clean_profile, default_config):
    # Create a fresh Transcriptor instance for each test
    config = Config(**default_config)
    t = Transcriptor(config=config, config_file=CONFIG_FILE)
    return t


def test_initialization(
    transcriptor, test_base_dir, default_config, default_profile
):
    """Test Transcriptor initializes with default config and profile"""
    # Verify config
    assert transcriptor.config.base_dir == str(test_base_dir)
    assert transcriptor.config.date_format == default_config["date_format"]
    assert CONFIG_FILE.exists()

    # Verify profile
    assert transcriptor.profile.name == default_profile["name"]
    assert transcriptor.profile.area == default_profile["area"]
    assert transcriptor.profile.country == default_profile["country"]
    assert PROFILE_FILE.exists()

    # Verify API initialization
    assert isinstance(transcriptor.api, API)
    assert transcriptor.api.base_dir == test_base_dir


def test_initialization_with_existing_config(test_base_dir, default_config):
    """Test initialization with existing config file"""
    # Create existing config
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(default_config, f)

    transcriptor = Transcriptor(config_file=CONFIG_FILE)

    assert transcriptor.config.base_dir == str(test_base_dir)
    assert transcriptor.config.date_format == default_config["date_format"]


def test_initialization_with_existing_profile(test_base_dir, default_profile):
    """Test initialization with existing profile file"""
    profile_data = {
        "name": "Test User",
        "area": "Test Area",
        "country": "Test Country",
    }
    # Create existing profile
    with open(PROFILE_FILE, "w") as f:
        yaml.dump(profile_data, f)

    transcriptor = Transcriptor(config_file=CONFIG_FILE)

    assert transcriptor.profile.name == profile_data["name"]
    assert transcriptor.profile.area == profile_data["area"]
    assert transcriptor.profile.country == profile_data["country"]


def test_save_config(transcriptor, test_base_dir):
    """Test saving config updates the file"""
    new_date_format = "%d-%m-%Y"
    transcriptor.config.date_format = new_date_format
    transcriptor.save_config(CONFIG_FILE)

    # Verify file was updated
    with open(CONFIG_FILE, "r") as f:
        saved_config = yaml.safe_load(f)
    assert saved_config["date_format"] == new_date_format


def test_save_profile(transcriptor, test_base_dir):
    """Test saving profile updates the file"""
    new_name = "Updated Name"
    transcriptor.profile.name = new_name
    transcriptor.save_profile(PROFILE_FILE)

    # Verify file was updated
    with open(PROFILE_FILE, "r") as f:
        saved_profile = yaml.safe_load(f)
    assert saved_profile["name"] == new_name


def test_create_client(transcriptor, test_base_dir):
    """Test client creation with default rates"""
    client_name = "Test Client"
    client_email = "test@example.com"

    transcriptor.create_client(name=client_name, email=client_email)

    # Verify client was created in database
    clients = transcriptor.api.get_clients(
        conditions={"name": [("=", client_name)]}
    )
    assert len(clients) == 1
    assert clients[0]["name"] == client_name
    assert clients[0]["email"] == client_email

    # Verify rates were created
    rates = transcriptor.api.get_rates(
        conditions={"client_id": [("=", clients[0]["id"])]}
    )
    assert len(rates) == 1
    assert rates[0]["normal"] == 0.4
    assert rates[0]["expedite"] == 0.6
    assert rates[0]["interpreted"] == 0.3

    # Verify client directory was created
    client_dir = test_base_dir / "clients" / "Test_Client"
    assert client_dir.exists()
    assert (client_dir / "templates").exists()


def test_create_client_with_custom_rates(transcriptor, test_base_dir):
    """Test client creation with custom rates"""
    client_name = "Custom Rate Client"
    client_email = "custom@example.com"
    custom_rates = {"normal": 0.5, "expedite": 0.7, "interpreted": 0.4}

    transcriptor.create_client(
        name=client_name, email=client_email, rates_dict=custom_rates
    )

    # Verify custom rates were set
    clients = transcriptor.api.get_clients(
        conditions={"name": [("=", client_name)]}
    )
    rates = transcriptor.api.get_rates(
        conditions={"client_id": [("=", clients[0]["id"])]}
    )
    assert rates[0]["normal"] == 0.5
    assert rates[0]["expedite"] == 0.7
    assert rates[0]["interpreted"] == 0.4


def test_create_job_dir(transcriptor, test_base_dir):
    """Test job directory creation"""
    client_name = "JobDirTest"
    job_number = "JOB123"
    date_received = "2023-06-15"
    date_due = "2023-06-20"

    # First create the client
    transcriptor.create_client(name=client_name, email="jobdir@test.com")

    job_dir = transcriptor.create_job_dir(
        client_name=client_name,
        job_number=job_number,
        date_received=date_received,
        date_due=date_due,
    )

    # Verify directory structure
    assert job_dir.exists()
    assert str(job_dir).endswith("15_Thu_JOB123_DUE_20_Tue")
    assert job_dir.parent.name == "June"
    assert job_dir.parent.parent.name == "2023"


@patch("lexiflow.base.shutil.copy")
@patch("lexiflow.base.shutil.copytree")
def test_mv_extract_job_file(mock_copytree, mock_copy, transcriptor):
    """Test job file movement/extraction"""
    test_file = Path("test_file.zip")
    test_dir = Path("test_dir")

    # Test with zip file
    with patch("lexiflow.base.zipfile.is_zipfile", return_value=True):
        with patch("lexiflow.base.zipfile.ZipFile") as mock_zip:
            mock_zip.return_value.__enter__.return_value.namelist.return_value = (
                []
            )
            transcriptor.mv_extract_job_file(test_file, test_dir)
            mock_zip.assert_called_once_with(test_file)

    # Test with regular file
    with patch("lexiflow.base.zipfile.is_zipfile", return_value=False):
        transcriptor.mv_extract_job_file(test_file, test_dir)
        mock_copy.assert_called_once_with(test_file, test_dir)


def test_mv_extract_job_file_rejects_path_traversal(
    transcriptor, test_base_dir, caplog
):
    """Zip members that escape the target directory must not be extracted."""
    zip_path = test_base_dir / "malicious.zip"
    job_dir = test_base_dir / "job_dir"
    job_dir.mkdir(exist_ok=True)

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.txt", "pwned")

    transcriptor.mv_extract_job_file(zip_path, job_dir)

    assert not (test_base_dir / "evil.txt").exists()
    assert "escapes target directory" in caplog.text


def test_mv_extract_job_file_ignores_bare_root_zip_entry(
    transcriptor, test_base_dir, caplog
):
    """A zip member literally named '/' (a harmless top-level directory
    entry some zip tools include) must not be flagged as a path-traversal
    escape -- pathlib's `job_dir / "/"` discards job_dir entirely and
    resolves to the filesystem root, which is what previously tripped the
    guard's `job_dir not in target.parents` check as a false positive."""
    zip_path = test_base_dir / "benign_with_root_entry.zip"
    job_dir = test_base_dir / "job_dir_root_entry"
    job_dir.mkdir(exist_ok=True)

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("/", "")
        zf.writestr("audio.mp3", "fake audio content")

    transcriptor.mv_extract_job_file(zip_path, job_dir)

    assert "escapes target directory" not in caplog.text
    assert (job_dir / "audio.mp3").exists()


def test_select_job_template(transcriptor, test_base_dir):
    """Test job template selection"""
    client_name = "TemplateTest"
    transcriptor.create_client(name=client_name, email="template@test.com")

    # Test with valid template
    template_path = transcriptor.select_job_template(client_name, "zd")
    assert template_path.exists()
    assert template_path.name == "Zoom Deposition Block Files.docx"

    # Test template directory was created
    client_template_dir = (
        test_base_dir / "clients" / "TemplateTest" / "templates"
    )
    assert client_template_dir.exists()


def test_generate_invoice(transcriptor):
    """Test invoice generation"""
    # Setup test client and jobs
    client_id = transcriptor.api.add_client(
        {"name": "InvoiceClient", "email": "invoice@test.com"}
    )
    job_data = {
        "client_id": client_id,
        "date_received": "2023-01-01",
        "job_number": "INV001",
        "job_type": "Normal",
        "status": "Done",
        "date_due": "2023-01-10",
        "total_quantity": 60.0,
        "quantity": 60.0,
        "job_rate": 0.4,
        "amount": 24.0,
        "amount_paid": 0.0,
        "job_path": "/path/to/job",
        "note": "Test invoice job",
        "date_submitted": "2023-01-05",
    }
    transcriptor.api.add_job(job_data)

    # Generate invoice
    invoice_jobs = transcriptor.get_invoice_jobs(
        client_id=client_id,
        conditions={"amount_paid": [("=", 0)]},
    )
    html, client_name = transcriptor.generate_invoice(
        invoice_jobs,
        invoice_theme="blue",
    )

    assert client_name == "InvoiceClient"
    assert "InvoiceClient" in html
    assert "INV001" in html
    assert "24.0" in html


@patch("lexiflow.base.fetch_rate", return_value=128.36)
def test_generate_invoice_with_conversion(mock_fetch_rate, transcriptor):
    """Invoices can be generated in the configured currency."""
    client_id = transcriptor.api.add_client(
        {"name": "ConvertClient", "email": "convert@test.com"}
    )
    job_data = {
        "client_id": client_id,
        "date_received": "2023-01-01",
        "job_number": "CONV001",
        "job_type": "Normal",
        "status": "Done",
        "date_due": "2023-01-10",
        "total_quantity": 60.0,
        "quantity": 60.0,
        "job_rate": 0.4,
        "amount": 24.0,
        "amount_paid": 0.0,
        "job_path": "/path/to/job",
        "note": "Test converted invoice job",
        "date_submitted": "2023-01-05",
    }
    transcriptor.api.add_job(job_data)

    transcriptor.config.invoice_currency = "KES"
    invoice_jobs = transcriptor.get_invoice_jobs(
        client_id=client_id,
        conditions={"amount_paid": [("=", 0)]},
    )
    html, client_name = transcriptor.generate_invoice(
        invoice_jobs, invoice_theme="blue"
    )

    assert client_name == "ConvertClient"
    assert "KSh" in html
    # USD amount should have been converted away
    assert ">24.0<" not in html
    mock_fetch_rate.assert_called_once()


@patch("lexiflow.base.htmlstr_to_pdf")
def test_html_to_pdf(mock_htmlstr_to_pdf, transcriptor, test_base_dir):
    """Test HTML to PDF conversion"""
    test_html = "<html><body>Test</body></html>"
    client_name = "PDFClient"

    transcriptor.html_to_pdf(test_html, client_name)

    # Verify directory was created
    invoice_dir = test_base_dir / "clients" / "PDFClient" / "invoices"
    assert invoice_dir.exists()

    # Verify PDF would be created with today's date
    today = date.today().strftime("%Y-%m-%d")
    invoice_dir / f"{today}_PDFClient_invoice.pdf"
    mock_htmlstr_to_pdf.assert_called_once()


def test_save_and_load_cutoffs(transcriptor, test_base_dir):
    """Test cutoff date saving and loading"""
    test_cutoffs = [
        ["Cutoff Date", "Deposit Date"],
        [date(2023, 1, 15), date(2023, 1, 20)],
        [date(2023, 2, 15), date(2023, 2, 20)],
    ]

    # Save cutoffs
    transcriptor.save_cutoffs(test_cutoffs)

    # Verify file was created
    cutoff_file = (
        test_base_dir / "cutoffs" / f"cutoffs_{date.today().year}.csv"
    )
    assert cutoff_file.exists()

    # Load cutoffs
    loaded_cutoffs = transcriptor.load_cutoffs()
    assert len(loaded_cutoffs) == 3
    assert loaded_cutoffs[1][0] == date(2023, 1, 15)
    assert loaded_cutoffs[2][1] == date(2023, 2, 20)


def test_select_cutoff_period(transcriptor):
    """Test cutoff period selection"""
    test_cutoffs = [
        [date(2023, 1, 15), date(2023, 1, 20)],
        [date(2023, 2, 15), date(2023, 2, 20)],
        [date(2023, 3, 15), date(2023, 3, 20)],
    ]

    # Mock loaded cutoffs
    # Test first period
    prev, curr = transcriptor.select_cutoff_period(1, cutoffs=test_cutoffs)
    assert prev is None
    assert curr == date(2023, 1, 15)

    # Test middle period
    prev, curr = transcriptor.select_cutoff_period(2, cutoffs=test_cutoffs)
    assert prev == date(2023, 1, 15)
    assert curr == date(2023, 2, 15)

    # Test last period
    prev, curr = transcriptor.select_cutoff_period(3, cutoffs=test_cutoffs)
    assert prev == date(2023, 2, 15)
    assert curr == date(2023, 3, 15)


def test_delete_clients_with_purge(transcriptor, test_base_dir):
    """Test client deletion with purge option"""
    client_name = "DeleteClient"
    transcriptor.create_client(name=client_name, email="delete@test.com")

    # Verify client exists
    clients = transcriptor.api.get_clients(
        conditions={"name": [("=", client_name)]}
    )
    assert len(clients) == 1

    # Delete with purge
    deleted = transcriptor.delete_clients(
        conditions={"name": [("=", client_name)]}, purge=True
    )

    assert len(deleted) == 1
    assert deleted[0]["name"] == client_name

    # Verify client directory was removed
    client_dir = test_base_dir / "clients" / "DeleteClient"
    assert not client_dir.exists()


def test_delete_jobs_with_purge(transcriptor, test_base_dir):
    """Test job deletion with purge option"""
    # Setup client and job
    client_id = transcriptor.api.add_client(
        {"name": "JobDeleteTest", "email": "jobdelete@test.com"}
    )
    job_data = {
        "client_id": client_id,
        "date_received": "2023-01-01",
        "job_number": "DEL001",
        "job_type": "Normal",
        "status": "Done",
        "date_due": "2023-01-10",
        "total_quantity": 60.0,
        "quantity": 60.0,
        "job_rate": 0.4,
        "amount": 24.0,
        "amount_paid": 0.0,
        "job_path": str(test_base_dir / "test_job_path"),
        "note": "Test job to delete",
        "date_submitted": "2023-01-05",
    }
    job_id = transcriptor.api.add_job(job_data)

    # Create dummy job directory
    job_dir = test_base_dir / "test_job_path"
    job_dir.mkdir(parents=True)

    # Delete with purge
    deleted = transcriptor.delete_jobs(
        conditions={"id": [("=", job_id)]}, purge=True
    )

    assert len(deleted) == 1
    assert not job_dir.exists()


def test_create_job_full_flow(transcriptor, test_base_dir):
    client_name = "FullJob"
    transcriptor.create_client(name=client_name, email="full@test.com")
    client_id = transcriptor.api.get_clients(
        conditions={"name": [("=", client_name)]}
    )[0]["id"]

    # Create dummy job file
    job_file = test_base_dir / "job.mp3"
    job_file.touch()

    job_info = {
        "client_id": client_id,
        "job_number": "FULL001",
        "date_received": "2023-01-01",
        "date_due": "2023-01-10",
    }

    # Callback to return task info
    def task_callback(task_file):
        return {
            "job_type": "Normal",
            "quantity": 10.0,
            "total_quantity": 10.0,
            "job_template": "zd",
            "note": "test",
            "date_due": "2023-01-10",
        }

    # Mock media utils to return our dummy file
    with patch("lexiflow.base.get_media_files", return_value=[job_file]):
        with patch(
            "lexiflow.base.next_non_existent_file",
            return_value=test_base_dir / "final_task.docx",
        ):
            transcriptor.create_job(str(job_file), job_info, task_callback)

    # Verify job created
    jobs = transcriptor.api.get_jobs(
        conditions={"job_number": [("=", "FULL001")]}
    )
    assert len(jobs) == 1
    assert jobs[0]["amount"] == 4.0  # 10 * 0.4


def test_get_summary_invoice_jobs(transcriptor):
    client_name = "SummaryClient"
    transcriptor.create_client(name=client_name, email="summary@test.com")
    client_id = transcriptor.api.get_clients(
        conditions={"name": [("=", client_name)]}
    )[0]["id"]

    # Add paid jobs in different months
    # Month 1
    job1 = {
        "client_id": client_id,
        "job_number": "S1",
        "status": "Done",
        "amount": 10.0,
        "amount_paid": 10.0,
        "date_received": "2023-01-01",
        "date_due": "2023-01-05",
        "date_submitted": "2023-01-10",
        "job_path": "path",
        "job_type": "Normal",
        "quantity": 1,
        "total_quantity": 1,
        "job_rate": 0.4,
    }
    transcriptor.api.add_job(job1)

    # Mock cutoffs
    cutoffs = [
        ["Cutoff", "Deposit"],
        [date(2023, 1, 31), date(2023, 2, 5)],
    ]
    with patch.object(transcriptor, "load_cutoffs", return_value=cutoffs):
        with patch.object(
            transcriptor,
            "select_cutoff_period",
            return_value=(date(2023, 1, 1), date(2023, 1, 31)),
        ):
            summary = transcriptor.get_summary_invoice_jobs(
                client_id, year=2023
            )

    assert client_name in summary
    assert len(summary[client_name]) == 1
    assert (
        summary[client_name][0]["month"] == "February"
    )  # Deposit date month
    assert summary[client_name][0]["total"] == 10.0


def test_generate_csv_invoice(transcriptor, test_base_dir):
    client_name = "CSVClient"
    transcriptor.create_client(name=client_name, email="csv@test.com")

    jobs = [
        {
            "job_number": "J1",
            "job_type": "Normal",
            "job_rate": 0.5,
            "quantity": 10,
            "amount": 5.0,
        }
    ]

    transcriptor.generate_csv_invoice(jobs, client_name)

    csv_dir = test_base_dir / "clients" / "CSVClient" / "invoices" / "csv"
    assert csv_dir.exists()
    assert len(list(csv_dir.glob("*.csv"))) == 1


def test_purge_job_files(transcriptor, test_base_dir):
    job_path = test_base_dir / "job_files" / "audio.mp3"
    job_path.parent.mkdir(parents=True)
    job_path.touch()

    jobs = [{"job_path": str(job_path)}]

    transcriptor.purge_job_files(jobs)
    assert not job_path.exists()


def test_get_invoice_jobs_no_id(transcriptor):
    assert transcriptor.get_invoice_jobs(None) == ("", "")


def test_get_invoice_jobs_raw_sql_rejects_invalid_client_id(
    transcriptor, caplog
):
    """A non-numeric client_id must not be interpolated into raw SQL."""
    result = transcriptor.get_invoice_jobs(
        client_id="1 OR 1=1", raw_sql_stmt="WHERE 1=1"
    )
    assert result is None
    assert "Invalid client_id" in caplog.text


def test_get_invoice_jobs_raw_sql_accepts_numeric_client_id(transcriptor):
    client_id = transcriptor.api.add_client(
        {"name": "RawSqlClient", "email": "raw@test.com"}
    )
    transcriptor.api.add_job(
        {
            "client_id": client_id,
            "date_received": "2023-01-01",
            "job_number": "RSQL001",
            "job_type": "Normal",
            "status": "Done",
            "date_due": "2023-01-10",
            "total_quantity": 10.0,
            "quantity": 10.0,
            "job_rate": 0.4,
            "amount": 4.0,
            "amount_paid": 0.0,
            "job_path": "/path",
            "note": "",
            "date_submitted": "2023-01-05",
        }
    )
    # client_id arrives as a string, mirroring the CLI's -c flag (untyped).
    result = transcriptor.get_invoice_jobs(
        client_id=str(client_id), raw_sql_stmt="WHERE 1=1"
    )
    assert result is not None
    assert len(result) == 1
    assert result[0]["job_number"] == "RSQL001"


def test_get_jobs_by_job_numbers_rejects_invalid_client_id(transcriptor):
    result = transcriptor.get_jobs_by_job_numbers(
        "1; DROP TABLE jobs", ["J1"]
    )
    assert result == []


def test_get_jobs_by_job_numbers_escapes_quotes_in_job_number(transcriptor):
    client_id = transcriptor.api.add_client(
        {"name": "QuoteClient", "email": "quote@test.com"}
    )
    quoted_job_number = "O'Brien-001"
    transcriptor.api.add_job(
        {
            "client_id": client_id,
            "date_received": "2023-01-01",
            "job_number": quoted_job_number,
            "job_type": "Normal",
            "status": "Pending",
            "date_due": "2023-01-10",
            "total_quantity": 10.0,
            "quantity": 10.0,
            "job_rate": 0.4,
            "amount": 4.0,
            "amount_paid": 0.0,
            "job_path": "/path",
            "note": "",
        }
    )

    # A job number containing a single quote must round-trip correctly
    # instead of breaking the SQL string literal it's embedded in.
    result = transcriptor.get_jobs_by_job_numbers(
        str(client_id), [quoted_job_number]
    )
    assert len(result) == 1
    assert result[0]["job_number"] == quoted_job_number


def test_generate_invoice_no_jobs(transcriptor):
    assert transcriptor.generate_invoice([]) == ("", "")


def test_get_summary_invoice_jobs_no_id(transcriptor):
    with patch.object(
        transcriptor, "load_cutoffs", return_value=[["Cutoff", "Deposit"]]
    ):
        assert transcriptor.get_summary_invoice_jobs(None) == {}


def test_get_summary_invoice_jobs_no_client(transcriptor):
    with patch.object(
        transcriptor, "load_cutoffs", return_value=[["Cutoff", "Deposit"]]
    ):
        assert transcriptor.get_summary_invoice_jobs(999) == {}


def test_mv_extract_job_file_error(transcriptor):
    # Pass a non-existent file to trigger error (it logs but doesn't raise usually)
    # Actually mv_extract_job_file uses shutil.copy which raises.
    # But wait, Transcriptor.mv_extract_job_file:
    # if zipfile.is_zipfile(job_file):
    #    try: ... except Exception as e: logger.error(...)
    # else: shutil.copy(job_file, job_dir)

    with pytest.raises(FileNotFoundError):
        transcriptor.mv_extract_job_file("non_existent.zip", "/tmp")


def test_create_job_no_client(transcriptor):
    # Should log error and return
    transcriptor.create_job("file.mp3", {"client_id": 999}, lambda x: {})


def test_load_cutoffs_not_found(transcriptor):
    # Pass a non-existent file
    with pytest.raises(FileNotFoundError):
        transcriptor.load_cutoffs(file_path="non_existent.csv")


def test_select_cutoff_period_first_year_prev(transcriptor, test_base_dir):
    # Test deposit_date_idx == 0 and previous year cutoffs logic
    cutoffs = [["Cutoff", "Deposit"], [date(2023, 1, 15), date(2023, 1, 20)]]
    # It is called 2 times total:
    # 1. cutoff_deposit_pairs = self.load_cutoffs(year=year)[1:]
    # 2. previous_year_cutoffs = self.load_cutoffs(year=previous_year)[1:]
    with patch.object(
        transcriptor,
        "load_cutoffs",
        side_effect=[cutoffs, Exception("no 2022")],
    ):
        prev, curr = transcriptor.select_cutoff_period(1, cutoffs=None)
        assert prev is None
        assert curr == date(2023, 1, 15)


def test_update_jobs_sync_files(transcriptor, test_base_dir):
    client_name = "SyncClient"
    transcriptor.create_client(name=client_name, email="sync@test.com")
    client_id = transcriptor.api.get_clients(
        conditions={"name": [("=", client_name)]}
    )[0]["id"]

    # Create a job with a file
    job_dir = transcriptor.create_job_dir(
        client_name, "SYNC001", "2023-01-01", "2023-01-10"
    )
    job_file = job_dir / "task.mp3"
    job_file.touch()

    job_data = {
        "client_id": client_id,
        "job_number": "SYNC001",
        "date_received": "2023-01-01",
        "date_due": "2023-01-10",
        "job_path": str(job_file),
        "status": "Pending",
        "amount": 0,
        "job_type": "Normal",
        "quantity": 0,
        "total_quantity": 0,
        "job_rate": 0,
    }
    job_id = transcriptor.api.add_job(job_data)

    # Update date_received - should trigger directory move
    new_date = "2023-02-01"
    transcriptor.update_jobs(
        conditions={"id": [("=", job_id)]}, values={"date_received": new_date}
    )

    # Verify new directory exists
    new_job_dir = transcriptor.create_job_dir(
        client_name, "SYNC001", new_date, "2023-01-10"
    )
    assert new_job_dir.exists()
    assert (new_job_dir / "task.mp3").exists()


def test_write_config_exception(transcriptor):
    with patch(
        "lexiflow.models.Config.write",
        side_effect=Exception("Write error"),
    ):
        with pytest.raises(RuntimeError):
            transcriptor._write_config()


def test_write_profile_exception(transcriptor):
    with patch(
        "lexiflow.models.Profile.write",
        side_effect=Exception("Write error"),
    ):
        with pytest.raises(RuntimeError):
            transcriptor._write_profile()


def test_load_profile_exception(transcriptor):
    # We need to ensure _profile_file_exists returns True first
    with patch.object(
        transcriptor, "_profile_file_exists", return_value=True
    ):
        with patch(
            "lexiflow.base.Profile.from_yaml",
            side_effect=Exception("Load error"),
        ):
            with pytest.raises(RuntimeError):
                transcriptor._load_profile()


def test_mv_extract_job_file_zip_error(transcriptor, caplog):
    with patch("zipfile.is_zipfile", return_value=True):
        with patch("zipfile.ZipFile", side_effect=Exception("Zip error")):
            transcriptor.mv_extract_job_file("bad.zip", "dest")
            assert "Could not extract zip file" in caplog.text


def test_create_job_client_not_found(transcriptor, caplog):
    transcriptor.create_job("job.mp3", {"client_id": 99999}, lambda x: {})
    assert "No client found" in caplog.text


def test_create_job_no_task_info(transcriptor, test_base_dir):
    # Setup valid client
    cid = transcriptor.api.add_client({"name": "NoTask", "email": "n@t.com"})

    # Mock create_job_dir to avoid fs ops
    with patch.object(transcriptor, "create_job_dir"):
        # Mock get_media_files to return something
        with patch(
            "lexiflow.base.get_media_files",
            return_value=[Path("file.mp3")],
        ):
            # task_callback returns None
            transcriptor.create_job(
                "job.mp3",
                {
                    "client_id": cid,
                    "job_number": "J1",
                    "date_received": "2023-01-01",
                    "date_due": "2023-01-02",
                },
                lambda x: None,
            )

    # Verify no job added
    jobs = transcriptor.api.get_jobs(conditions={"client_id": [("=", cid)]})
    assert len(jobs) == 0


def test_get_where_clause_none(transcriptor):
    assert transcriptor._get_where_clause_from_update_sql(None) is None


def test_get_update_client_name_raw(transcriptor):
    cid = transcriptor.api.add_client(
        {"name": "RawClient", "email": "r@c.com"}
    )
    name = transcriptor._get_update_client_name(
        None, None, f"SET client_id={cid} WHERE id=1"
    )
    assert name == "RawClient"


def test_read_invoice_counter_malformed(transcriptor, tmp_path):
    f = tmp_path / "counter"
    f.write_text("invalid")
    with pytest.raises(ValueError):
        transcriptor.read_invoice_counter(f)


def test_increase_invoice_counter_malformed(transcriptor, tmp_path):
    f = tmp_path / "counter"
    f.write_text("invalid")
    transcriptor.increase_invoice_counter(f)
    assert f.read_text() == "00002"


def test_purge_job_files_exception(transcriptor, test_base_dir, caplog):
    # Create a file that fails to unlink
    f = test_base_dir / "protected.mp3"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch()
    with patch("pathlib.Path.unlink", side_effect=OSError("Access denied")):
        transcriptor.purge_job_files([{"job_path": str(f)}])
        assert "Error deleting file" in caplog.text


def test_update_jobs_raw_sql_set_path(transcriptor):
    cid = transcriptor.api.add_client({"name": "SetPath", "email": "s@p.com"})
    # Add job_type="Normal"
    jid = transcriptor.api.add_job(
        {
            "client_id": cid,
            "job_number": "SP1",
            "status": "Pending",
            "job_path": "/tmp/old/file.mp3",
            "date_received": "2023-01-01",
            "date_due": "2023-01-05",
            "job_type": "Normal",
            "total_quantity": 0,
            "quantity": 0,
            "job_rate": 0,
            "amount": 0,
        }
    )

    with patch.object(
        transcriptor, "_sync_job_files", return_value="/tmp/new/file.mp3"
    ):
        with patch.object(transcriptor.api, "update_jobs") as mock_update:
            transcriptor.update_jobs(
                raw_sql_stmt=f"SET status='Done' WHERE id={jid}"
            )
            # Check if raw_sql_stmt was modified
            args = mock_update.call_args
            assert (
                'set job_path="/tmp/new/file.mp3", '
                in args.kwargs["raw_sql_stmt"]
            )


def test_delete_jobs_raw_sql(transcriptor):
    # Mock api.delete_jobs to return list
    with patch.object(
        transcriptor.api,
        "delete_jobs",
        return_value=[{"job_path": "/tmp/j1"}],
    ) as mock_del:
        transcriptor.delete_jobs(raw_sql_stmt="WHERE id=1", purge=False)
        mock_del.assert_called_with(
            conditions=None, raw_sql_stmt="WHERE id=1"
        )


# -------- transcription-provider wiring (Phase 2) --------


def _make_transcription_job(transcriptor, test_base_dir, **overrides):
    unique = datetime.now().timestamp()
    client_id = transcriptor.api.add_client(
        {
            "name": overrides.pop(
                "client_name", f"TranscriptionClient {unique}"
            ),
            "email": "tx@test.com",
        }
    )
    job_file = test_base_dir / f"audio_{unique}.mp3"
    job_file.write_text("fake audio")
    job_data = {
        "client_id": client_id,
        "date_received": "2023-01-01",
        "job_number": overrides.pop("job_number", "TX001"),
        "job_type": "Normal",
        "status": "Pending",
        "date_due": "2023-01-10",
        "total_quantity": 10.0,
        "quantity": 10.0,
        "job_rate": 0.4,
        "amount": 4.0,
        "amount_paid": 0.0,
        "job_path": str(job_file),
        "note": "",
    }
    job_data.update(overrides)
    job_id = transcriptor.api.add_job(job_data)
    return job_id, job_file


def test_submit_transcription_updates_job_row(transcriptor, test_base_dir):
    job_id, job_file = _make_transcription_job(transcriptor, test_base_dir)

    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-123"

    with patch(
        "lexiflow.base.get_service", return_value=mock_service
    ) as mock_get_service:
        external_id = asyncio.run(
            transcriptor.submit_transcription(job_id, "revai")
        )

    assert external_id == "ext-123"
    mock_get_service.assert_called_once_with("revai")
    mock_service.submit_job.assert_awaited_once_with(
        job_file, additional_vocabulary=None
    )
    mock_service.close.assert_awaited_once()

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["provider"] == "revai"
    assert job["external_job_id"] == "ext-123"
    assert job["transcription_status"] == "in_progress"


def test_submit_transcription_passes_vocabulary(transcriptor, test_base_dir):
    job_id, job_file = _make_transcription_job(transcriptor, test_base_dir)
    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-1"

    with patch("lexiflow.base.get_service", return_value=mock_service):
        asyncio.run(
            transcriptor.submit_transcription(
                job_id, "revai", additional_vocabulary=["Plaintiff"]
            )
        )

    mock_service.submit_job.assert_awaited_once_with(
        job_file, additional_vocabulary=["Plaintiff"]
    )


def test_submit_transcription_missing_job_raises(transcriptor):
    with pytest.raises(ValueError, match="No job found"):
        asyncio.run(transcriptor.submit_transcription(999999, "revai"))


def test_submit_transcription_missing_file_raises(transcriptor, test_base_dir):
    job_id, job_file = _make_transcription_job(transcriptor, test_base_dir)
    job_file.unlink()

    with pytest.raises(FileNotFoundError):
        asyncio.run(transcriptor.submit_transcription(job_id, "revai"))


def test_poll_transcription_status_updates_job(transcriptor, test_base_dir):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
        transcription_status="in_progress",
    )

    mock_service = AsyncMock()
    mock_service.get_job_status.return_value = {
        "id": "ext-123",
        "status": "transcribed",
    }

    with patch("lexiflow.base.get_service", return_value=mock_service):
        status = asyncio.run(transcriptor.poll_transcription_status(job_id))

    assert status == "transcribed"
    mock_service.get_job_status.assert_awaited_once_with("ext-123")
    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_status"] == "transcribed"


def test_poll_transcription_status_no_provider_returns_none(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(transcriptor, test_base_dir)

    with patch("lexiflow.base.get_service") as mock_get_service:
        status = asyncio.run(transcriptor.poll_transcription_status(job_id))

    assert status is None
    mock_get_service.assert_not_called()


def test_poll_transcription_status_failed_poll_returns_none(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
    )
    mock_service = AsyncMock()
    mock_service.get_job_status.return_value = None

    with patch("lexiflow.base.get_service", return_value=mock_service):
        status = asyncio.run(transcriptor.poll_transcription_status(job_id))

    assert status is None
    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_status"] is None


def test_fetch_transcript_writes_file_and_updates_status(
    transcriptor, test_base_dir
):
    job_id, job_file = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
        transcription_status="in_progress",
    )
    mock_service = AsyncMock()
    mock_service.get_transcript.return_value = "Hello, this is the transcript."

    with patch("lexiflow.base.get_service", return_value=mock_service):
        transcript_path = asyncio.run(transcriptor.fetch_transcript(job_id))

    assert transcript_path == job_file.parent / "TX001_transcript.txt"
    assert transcript_path.read_text() == "Hello, this is the transcript."
    mock_service.get_transcript.assert_awaited_once_with(
        "ext-123", metadata=None
    )
    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_status"] == "transcribed"


def test_fetch_transcript_passes_metadata(transcriptor, test_base_dir):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="notebooklm",
        external_job_id="src-1",
    )
    mock_service = AsyncMock()
    mock_service.get_transcript.return_value = "text"
    metadata = {"WITNESS_NAME": "Jane Doe"}

    with patch("lexiflow.base.get_service", return_value=mock_service):
        asyncio.run(transcriptor.fetch_transcript(job_id, metadata=metadata))

    mock_service.get_transcript.assert_awaited_once_with(
        "src-1", metadata=metadata
    )


def test_fetch_transcript_missing_provider_raises(transcriptor, test_base_dir):
    job_id, _ = _make_transcription_job(transcriptor, test_base_dir)

    with pytest.raises(ValueError, match="no provider/external_job_id"):
        asyncio.run(transcriptor.fetch_transcript(job_id))


# -------- polling metadata (last_polled_at / last_error) --------


def test_submit_transcription_records_error_and_reraises(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(transcriptor, test_base_dir)
    mock_service = AsyncMock()
    mock_service.submit_job.side_effect = RuntimeError("provider unreachable")

    with patch("lexiflow.base.get_service", return_value=mock_service):
        with pytest.raises(RuntimeError, match="provider unreachable"):
            asyncio.run(transcriptor.submit_transcription(job_id, "revai"))

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_error"] == "provider unreachable"
    # A failed submit never got far enough to set these.
    assert job["provider"] is None
    assert job["external_job_id"] is None


def test_submit_transcription_clears_previous_error_on_success(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        transcription_last_error="stale error from a previous attempt",
    )
    mock_service = AsyncMock()
    mock_service.submit_job.return_value = "ext-1"

    with patch("lexiflow.base.get_service", return_value=mock_service):
        asyncio.run(transcriptor.submit_transcription(job_id, "revai"))

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_error"] is None


def test_poll_transcription_status_sets_last_polled_at_on_success(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
        transcription_last_error="stale error",
    )
    mock_service = AsyncMock()
    mock_service.get_job_status.return_value = {"status": "transcribed"}

    with patch("lexiflow.base.get_service", return_value=mock_service):
        asyncio.run(transcriptor.poll_transcription_status(job_id))

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_polled_at"] is not None
    assert job["transcription_last_error"] is None


def test_poll_transcription_status_records_error_when_poll_returns_none(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
    )
    mock_service = AsyncMock()
    mock_service.get_job_status.return_value = None

    with patch("lexiflow.base.get_service", return_value=mock_service):
        asyncio.run(transcriptor.poll_transcription_status(job_id))

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_polled_at"] is not None
    assert job["transcription_last_error"]


def test_poll_transcription_status_records_error_and_reraises_on_exception(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
    )
    mock_service = AsyncMock()
    mock_service.get_job_status.side_effect = RuntimeError("network error")

    with patch("lexiflow.base.get_service", return_value=mock_service):
        with pytest.raises(RuntimeError, match="network error"):
            asyncio.run(transcriptor.poll_transcription_status(job_id))

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_polled_at"] is not None
    assert job["transcription_last_error"] == "network error"


def test_poll_transcription_status_no_provider_does_not_touch_polling_fields(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(transcriptor, test_base_dir)

    with patch("lexiflow.base.get_service") as mock_get_service:
        asyncio.run(transcriptor.poll_transcription_status(job_id))

    mock_get_service.assert_not_called()
    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_polled_at"] is None


def test_fetch_transcript_records_error_and_reraises(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
    )
    mock_service = AsyncMock()
    mock_service.get_transcript.side_effect = RuntimeError("fetch failed")

    with patch("lexiflow.base.get_service", return_value=mock_service):
        with pytest.raises(RuntimeError, match="fetch failed"):
            asyncio.run(transcriptor.fetch_transcript(job_id))

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_error"] == "fetch failed"
    assert job["transcription_status"] != "transcribed"


def test_fetch_transcript_clears_previous_error_on_success(
    transcriptor, test_base_dir
):
    job_id, _ = _make_transcription_job(
        transcriptor,
        test_base_dir,
        provider="revai",
        external_job_id="ext-123",
        transcription_last_error="stale error",
    )
    mock_service = AsyncMock()
    mock_service.get_transcript.return_value = "transcript text"

    with patch("lexiflow.base.get_service", return_value=mock_service):
        asyncio.run(transcriptor.fetch_transcript(job_id))

    job = transcriptor.api.get_jobs(conditions={"id": [("=", job_id)]})[0]
    assert job["transcription_last_error"] is None
