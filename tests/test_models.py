from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from yaml.scanner import ScannerError

from lexiflow.models import (
    Base,
    Client,
    Config,
    Invoice,
    InvoiceLine,
    Job,
    Profile,
    Rate,
)

# Test data constants
TEST_DB = "test_models.db"
TEST_YAML_FILE = "test_config.yaml"
SAMPLE_DATE = date(2023, 1, 1)


@pytest.fixture(scope="module")
def test_db_engine():
    """Create an in-memory SQLite database for testing"""
    engine = sa.create_engine(f"sqlite:///{TEST_DB}")
    Base.metadata.create_all(engine)
    yield engine
    # Teardown
    engine.dispose()
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


@pytest.fixture
def db_session(test_db_engine):
    """Create a new database session for each test"""
    Session = sessionmaker(bind=test_db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_client():
    return Client(
        name=f"Test Client {datetime.now().timestamp()}",
        email="test@example.com",
    )


@pytest.fixture
def sample_rate(sample_client):
    return Rate(
        normal=0.4, expedite=0.6, interpreted=0.3, client=sample_client
    )


@pytest.fixture
def sample_job(sample_client):
    return Job(
        client=sample_client,
        date_received="2023-01-01",
        job_number="JOB001",
        job_type="Normal",
        status="Pending",
        date_due="2023-01-10",
        total_quantity=60.0,
        quantity=60.0,
        job_rate=0.4,
        amount=24.0,
        job_path="/path/to/job",
    )


def test_client_model(db_session, sample_client):
    """Test Client model creation and relationships"""
    db_session.add(sample_client)
    db_session.commit()

    client = db_session.query(Client).first()
    assert "Test Client" in client.name
    assert "test@example.com" in client.email
    assert client.rate is None  # Not yet set


def test_rate_model(db_session, sample_client, sample_rate):
    """Test Rate model and relationship to Client"""
    sample_client.rate = sample_rate
    db_session.add_all([sample_client, sample_rate])
    db_session.commit()

    rate = db_session.query(Rate).first()
    assert rate.normal == 0.4
    assert "Test Client" in rate.client.name
    assert rate.client.rate == rate  # Back reference


def test_job_model(db_session, sample_client, sample_job):
    """Test Job model and relationships"""
    db_session.add_all([sample_client, sample_job])
    db_session.commit()

    job = db_session.query(Job).first()
    assert job.job_number == "JOB001"
    assert "Test Client" in job.client.name
    assert job.amount == 24.0  # quantity * job_rate


def test_job_model_provider_tracking_columns_default_none(
    db_session, sample_client, sample_job
):
    """provider/external_job_id/transcription_status are optional and don't
    affect existing (LegatoFlow-independent) jobs."""
    db_session.add_all([sample_client, sample_job])
    db_session.commit()

    job = db_session.query(Job).first()
    assert job.provider is None
    assert job.external_job_id is None
    assert job.transcription_status is None


def test_job_model_provider_tracking_columns_settable(
    db_session, sample_client
):
    job = Job(
        client=sample_client,
        date_received="2023-01-01",
        job_number="JOB004",
        job_type="Normal",
        status="Pending",
        date_due="2023-01-10",
        total_quantity=60.0,
        quantity=60.0,
        job_rate=0.4,
        amount=24.0,
        job_path="/path/to/job",
        provider="revai",
        external_job_id="abc123",
        transcription_status="in_progress",
    )
    db_session.add(job)
    db_session.commit()

    saved = db_session.query(Job).filter_by(job_number="JOB004").first()
    assert saved.provider == "revai"
    assert saved.external_job_id == "abc123"
    assert saved.transcription_status == "in_progress"


def test_job_model_polling_metadata_columns_default_none(
    db_session, sample_client, sample_job
):
    db_session.add_all([sample_client, sample_job])
    db_session.commit()

    job = db_session.query(Job).first()
    assert job.transcription_last_polled_at is None
    assert job.transcription_last_error is None


def test_job_model_polling_metadata_columns_settable(db_session, sample_client):
    job = Job(
        client=sample_client,
        date_received="2023-01-01",
        job_number="JOB005",
        job_type="Normal",
        status="Pending",
        date_due="2023-01-10",
        total_quantity=60.0,
        quantity=60.0,
        job_rate=0.4,
        amount=24.0,
        job_path="/path/to/job",
        transcription_last_polled_at="2023-01-01T12:00:00",
        transcription_last_error="Connection timed out",
    )
    db_session.add(job)
    db_session.commit()

    saved = db_session.query(Job).filter_by(job_number="JOB005").first()
    assert saved.transcription_last_polled_at == "2023-01-01T12:00:00"
    assert saved.transcription_last_error == "Connection timed out"


def test_job_amount_trigger(db_session, sample_client):
    """Test the trigger that updates amount when rate or quantity changes"""
    job = Job(
        client=sample_client,
        job_number="JOB002",
        job_type="Normal",
        total_quantity=60.0,
        quantity=60.0,
        job_rate=0.4,
        amount=24.0,
        date_received="2023-01-01",
        date_due="2023-01-10",
        job_path="/job/path",
    )
    db_session.add(job)
    db_session.commit()

    # Initial amount should be calculated
    assert job.amount == 24.0  # 60 * 0.4

    # Update quantity - amount should auto-update
    job.quantity = 30.0
    db_session.commit()
    assert job.amount == 12.0  # 30 * 0.4

    # Update rate - amount should auto-update
    job.job_rate = 0.5
    db_session.commit()
    assert job.amount == 15.0  # 30 * 0.5


def test_job_status_trigger(db_session, sample_client):
    """Test the trigger that updates date_submitted when status changes"""
    job = Job(
        client=sample_client,
        job_number="JOB003",
        status="Pending",
        date_received="2023-01-01",
        date_due="2023-01-10",
        job_type="Normal",
        total_quantity=60.0,
        quantity=60.0,
        job_rate=0.4,
        amount=24.0,
        job_path="/job/path",
    )
    db_session.add(job)
    db_session.commit()

    assert job.date_submitted is None

    # Change status to Done - should set date_submitted
    job.status = "Done"
    db_session.commit()
    assert job.date_submitted is not None

    # Change back to Pending - should clear date_submitted
    job.status = "Pending"
    db_session.commit()
    assert job.date_submitted is None


def test_yaml_base_config():
    """Test Config model YAML serialization"""
    config = Config(
        base_dir="/test/path", date_format="%Y-%m-%d", invoice_theme="default"
    )

    # Test writing to YAML
    mock_file = mock_open()
    with patch("builtins.open", mock_file):
        with patch("yaml.dump") as mock_dump:
            config.write(Path(TEST_YAML_FILE))

            # Verify file was opened in write mode
            mock_file.assert_called_once_with(Path(TEST_YAML_FILE), "w")

            # Verify yaml.dump was called with the config data
            mock_dump.assert_called_once_with(
                {
                    "base_dir": "/test/path",
                    "date_format": "%Y-%m-%d",
                    "invoice_theme": "default",
                    "display_currency": "USD",
                    "conversion_rate": 0.0,
                    "currency_segment": "",
                    "currency_receive_country": "",
                    "currency_send_country": "us",
                    "invoice_currency": "USD",
                },
                mock_file.return_value,
            )


def test_invoice_model():
    """Test Invoice model and due date calculation"""
    lines = [
        InvoiceLine(
            job_number="JOB001",
            job_type="Normal",
            job_rate=0.4,
            quantity=60.0,
        ),
        InvoiceLine(
            job_number="JOB002",
            job_type="Expedite",
            job_rate=0.6,
            quantity=30.0,
        ),
    ]
    profile = Profile(name="Tester")
    invoice = Invoice(
        profile=profile,
        invoice_number="INV001",
        client_name="Test Client",
        jobs=lines,
    )

    assert len(invoice.jobs) == 2
    assert invoice.due_date == invoice.create_date + timedelta(days=7)
    assert sum(job.amount for job in invoice.jobs) == pytest.approx(
        24.0 + 18.0
    )


def test_yaml_base_error_handling():
    """Test YAMLBase error handling"""
    # Test file not found
    with patch(
        "builtins.open", side_effect=FileNotFoundError("File not found")
    ):
        with pytest.raises(
            FileNotFoundError
        ):  # Changed to catch either error
            Config.from_yaml(Path("nonexistent.yaml"))
    # Test invalid YAML - need to actually provide invalid YAML
    invalid_yaml = "invalid: yaml: here\n  - bad: indentation\n"
    with patch("builtins.open", mock_open(read_data=invalid_yaml)):
        with pytest.raises(ScannerError):  # Changed to catch either error
            Config.from_yaml(Path(TEST_YAML_FILE))


def test_profile_defaults():
    """Test Profile model default values"""
    profile = Profile()
    assert profile.name == ""
    assert profile.area == ""
    assert profile.country == ""


def test_invoice_custom_due_date():
    """Test Invoice model with custom due date"""
    custom_date = date(2023, 12, 31)
    profile = Profile(name="Tester")
    invoice = Invoice(
        profile=profile,
        invoice_number="INV002",
        client_name="Test Client",
        jobs=[],
        due_date=custom_date,
    )

    assert invoice.create_date == date.today()
    assert invoice.due_date == custom_date


def test_yaml_base_write_error():
    config = Config(base_dir="/tmp", date_format="", invoice_theme="")

    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError):
            config.write(Path("bad.yaml"))

    with patch("builtins.open", mock_open()):
        with patch("yaml.dump", side_effect=Exception("Generic error")):
            with pytest.raises(Exception):
                config.write(Path("test.yaml"))
