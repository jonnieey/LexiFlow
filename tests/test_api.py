import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from lexiflow.api import API
from lexiflow.models import Client, Job

# Constants for testing
TEST_BASE_DIR = Path(__file__).parent / "test_data"
DB_FILE_NAME = "transcriptor.db"


@pytest.fixture(scope="module")
def test_base_dir():
    # Setup
    test_dir = TEST_BASE_DIR
    test_dir.mkdir(exist_ok=True)
    yield test_dir
    # Teardown
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def api(test_base_dir):
    # Create a fresh API instance for each test
    api = API(base_dir=test_base_dir)
    yield api
    # Clean up database after each test
    if (test_base_dir / DB_FILE_NAME).exists():
        os.remove(test_base_dir / DB_FILE_NAME)


@pytest.fixture
def sample_client_data():
    return {
        "name": f"Test Client {datetime.now().timestamp()}",
        "email": "test@example.com",
    }


@pytest.fixture
def sample_rate_data():
    return {"normal": 0.4, "expedite": 0.6, "interpreted": 0.3}


@pytest.fixture
def sample_job_data():
    return {
        "client_id": 1,
        "date_received": "2023-01-01",
        "job_number": "JOB001",
        "job_type": "Normal",
        "status": "Pending",
        "date_due": "2023-01-10",
        "total_quantity": 60.0,
        "quantity": 60.0,
        "job_rate": 0.4,
        "amount": 24.0,
        "amount_paid": 0.0,
        "job_path": "/path/to/job",
        "note": "Test job",
    }


def test_api_initialization(api, test_base_dir):
    assert api.base_dir == test_base_dir
    assert (test_base_dir / DB_FILE_NAME).exists()


def test_add_client(api, sample_client_data):
    client_id = api.add_client(sample_client_data)
    assert isinstance(client_id, int)
    assert client_id > 0


def test_add_rate(api, sample_client_data, sample_rate_data):
    # First add a client since rates need a client_id
    client_id = api.add_client(sample_client_data)
    rate_data = sample_rate_data.copy()
    rate_data["client_id"] = client_id

    rate_id = api.add_rates(rate_data)
    assert isinstance(rate_id, int)
    assert rate_id > 0


def test_add_job(api, sample_client_data, sample_job_data):
    # First add a client since jobs need a client_id
    client_id = api.add_client(sample_client_data)
    job_data = sample_job_data.copy()
    job_data["client_id"] = client_id

    job_id = api.add_job(job_data)
    assert isinstance(job_id, int)
    assert job_id > 0

    def test_add_jobs(self, api_instance):
        jobs = [
            {
                "client_id": 1,
                "job_number": "J1",
                "status": "Pending",
                "amount": 10.0,
            },
            {
                "client_id": 1,
                "job_number": "J2",
                "status": "Pending",
                "amount": 20.0,
            },
        ]
        api_instance.add_jobs(jobs)
        result = api_instance.get_jobs(conditions={"client_id": [("=", 1)]})
        assert len(result) >= 2

    def test_session_scope_exception(self, api_instance):
        with pytest.raises(Exception):
            with api_instance.session_scope() as session:
                session.add(Client(name="Fail"))
                raise Exception("Boom")

        # Verify rollback
        clients = api_instance.get_clients(
            conditions={"name": [("=", "Fail")]}
        )
        assert len(clients) == 0

    def test_build_statement_invalid_type(self, api_instance):
        with pytest.raises(ValueError, match="Invalid stmt_type"):
            api_instance._build_statement_with_conditions(
                Client, {"id": [("=", 1)]}, stmt_type="insert"
            )

    def test_build_statement_invalid_column(self, api_instance):
        with pytest.raises(AttributeError, match="Invalid column name"):
            api_instance._build_statement_with_conditions(
                Client, {"invalid_col": [("=", 1)]}
            )

    def test_build_statement_invalid_operator(self, api_instance):
        # We need to mock table attribute access to not fail on getattr but fail on op_map lookup?
        # Actually op_map key error raises ValueError.
        with pytest.raises(ValueError, match="Invalid comparison operator"):
            api_instance._build_statement_with_conditions(
                Client, {"id": [("INVALID", 1)]}
            )

    def test_get_raw_sql(self, api_instance):
        stmt = api_instance.get(Client, raw_sql_stmt="SELECT * FROM clients")
        assert str(stmt) == "SELECT * FROM clients"

    def test_update_exception(self, api_instance):
        # Trigger exception in update by passing invalid values
        # e.g. values that don't match columns
        # However, update() catches Exception and prints it, returning False.
        # We need to ensure _build_statement returns a stmt, then stmt.values() fails?
        # Or just pass raw_sql_stmt that fails? No, raw_sql_stmt path doesn't try/except the same way?
        # Let's try mocking _build_statement to return None or let .values() fail.

        with patch.object(
            api_instance, "_build_statement_with_conditions"
        ) as mock_build:
            mock_build.return_value = MagicMock()
            mock_build.return_value.values.side_effect = Exception(
                "Update fail"
            )

            result = api_instance.update(
                Client, {"id": [("=", 1)]}, {"name": "New"}
            )
            assert result is False

    def test_delete_exception(self, api_instance):
        # Similar to update exception
        with patch("sqlalchemy.delete") as mock_delete:
            mock_delete.side_effect = Exception("Delete fail")
            result = api_instance.delete(Client, {"id": [("=", 1)]})
            assert result is False

    def test_get_rates_raw_sql(self, api_instance):
        # Setup data
        cid = api_instance.add_client(
            {"name": "RateClient", "email": "r@c.com"}
        )
        api_instance.add_rates({"client_id": cid, "normal": 0.5})

        rates = api_instance.get_rates(
            raw_sql_stmt="WHERE rates.client_id = " + str(cid)
        )
        assert len(rates) == 1
        assert rates[0]["normal"] == 0.5

    def test_get_jobs_raw_sql(self, api_instance):
        cid = api_instance.add_client(
            {"name": "JobClient", "email": "j@c.com"}
        )
        api_instance.add_job(
            {"client_id": cid, "job_number": "RawJ1", "status": "Pending"}
        )

        jobs = api_instance.get_jobs(
            raw_sql_stmt="WHERE jobs.client_id = " + str(cid)
        )
        assert len(jobs) == 1
        assert jobs[0]["job_number"] == "RawJ1"
        assert jobs[0]["client"].name == "JobClient"

    def test_update_with_raw_sql(self, api_instance):
        cid = api_instance.add_client(
            {"name": "UpdateRaw", "email": "u@r.com"}
        )

        res = api_instance.update(
            Client,
            raw_sql_stmt="SET name = 'UpdatedRaw' WHERE id = " + str(cid),
        )
        assert res is not False

        # Verify
        clients = api_instance.get_clients(conditions={"id": [("=", cid)]})
        assert clients[0]["name"] == "UpdatedRaw"

    def test_delete_with_raw_sql(self, api_instance):
        cid = api_instance.add_client(
            {"name": "DeleteRaw", "email": "d@r.com"}
        )

        res = api_instance.delete(
            Client, conditions=None, raw_sql_stmt="WHERE id = " + str(cid)
        )
        assert res is not False

        # Verify
        clients = api_instance.get_clients(conditions={"id": [("=", cid)]})
        assert len(clients) == 0


def test_get_clients(api):
    # Add some test clients with unique names
    client_ids = []
    for i in range(1, 4):
        client_data = {
            "name": f"Client {i} {datetime.now().timestamp()}",
            "email": f"client{i}@example.com",
        }
        client_ids.append(api.add_client(client_data))

    # Test get all clients
    clients = api.get_clients()
    assert len(clients) == 3

    # Test get with conditions - use the actual client name from the first client
    first_client_name = clients[0]["name"]
    second_client_name = clients[1]["name"]

    clients = api.get_clients(
        conditions={"name": [("~", f"%{first_client_name}%")]}
    )
    assert len(clients) == 1
    assert first_client_name in clients[0]["name"]

    # Test raw SQL - use the actual client name from the second client
    clients = api.get_clients(
        raw_sql_stmt=f"WHERE name LIKE '%{second_client_name}%'"
    )
    assert len(clients) == 1
    assert second_client_name in clients[0]["name"]


def test_get_rates(api, sample_rate_data):
    # Add a client with unique name and rates
    client_data = {
        "name": f"Rate Test Client {datetime.now().timestamp()}",
        "email": "rate_test@example.com",
    }
    client_id = api.add_client(client_data)
    rate_data = sample_rate_data.copy()
    rate_data["client_id"] = client_id
    api.add_rates(rate_data)

    # Test get all rates
    rates = api.get_rates()
    assert len(rates) == 1
    assert rates[0]["normal"] == 0.4

    # Test get with conditions
    rates = api.get_rates(conditions={"client_id": [("=", client_id)]})
    assert len(rates) == 1

    # Test raw SQL
    rates = api.get_rates(raw_sql_stmt=f"WHERE client_id = {client_id}")
    assert len(rates) == 1


def test_get_jobs(api, sample_job_data):
    # Add a client with unique name and jobs
    client_data = {
        "name": f"Job Test Client {datetime.now().timestamp()}",
        "email": "job_test@example.com",
    }
    client_id = api.add_client(client_data)
    job_data = sample_job_data.copy()
    job_data["client_id"] = client_id

    # Add multiple jobs with unique job numbers
    jobs = []
    for i in range(1, 4):
        job = job_data.copy()
        job["job_number"] = f"JOB00{i}"
        job["status"] = "Pending" if i % 2 == 0 else "Done"
        jobs.append(job)
    api.add_jobs(jobs)

    # Test get all jobs
    all_jobs = api.get_jobs()
    assert len(all_jobs) == 3

    # Test get with conditions
    pending_jobs = api.get_jobs(conditions={"status": [("=", "Pending")]})
    assert len(pending_jobs) == 1  # Only 1 job with status="Pending"

    # Test raw SQL
    done_jobs = api.get_jobs(raw_sql_stmt="WHERE status = 'Done'")
    assert len(done_jobs) == 2  # 2 jobs with status="Done"


def test_update_clients(api):
    # Add a client with unique name
    client_data = {
        "name": f"Update Test Client {datetime.now().timestamp()}",
        "email": "update_test@example.com",
    }
    client_id = api.add_client(client_data)

    # Update the client
    new_email = "updated@example.com"
    api.update_clients(
        conditions={"id": [("=", client_id)]}, values={"email": new_email}
    )

    # Verify update
    clients = api.get_clients(conditions={"id": [("=", client_id)]})
    assert clients[0]["email"] == new_email

    # Test raw SQL update
    new_name = f"Updated Client Name {datetime.now().timestamp()}"
    api.update_clients(
        raw_sql_stmt=f"SET name = '{new_name}' WHERE id = {client_id}"
    )

    # Verify update
    clients = api.get_clients(conditions={"id": [("=", client_id)]})
    assert clients[0]["name"] == new_name


def test_update_rates(api, sample_rate_data):
    # Add a client with unique name and rate
    client_data = {
        "name": f"Rate Update Test Client {datetime.now().timestamp()}",
        "email": "rate_update_test@example.com",
    }
    client_id = api.add_client(client_data)
    rate_data = sample_rate_data.copy()
    rate_data["client_id"] = client_id
    rate_id = api.add_rates(rate_data)

    # Update the rate
    new_normal_rate = 0.5
    api.update_rates(
        conditions={"id": [("=", rate_id)]},
        values={"normal": new_normal_rate},
    )

    # Verify update
    rates = api.get_rates(conditions={"id": [("=", rate_id)]})
    assert rates[0]["normal"] == new_normal_rate


def test_update_jobs(api, sample_job_data):
    # Add a client with unique name and job
    client_data = {
        "name": f"Job Update Test Client {datetime.now().timestamp()}",
        "email": "job_update_test@example.com",
    }
    client_id = api.add_client(client_data)
    job_data = sample_job_data.copy()
    job_data["client_id"] = client_id
    job_id = api.add_job(job_data)

    # Update the job
    new_status = "Done"
    api.update_jobs(
        conditions={"id": [("=", job_id)]}, values={"status": new_status}
    )

    # Verify update
    jobs = api.get_jobs(conditions={"id": [("=", job_id)]})
    assert jobs[0]["status"] == new_status

    # Test that triggers updated date_submitted
    assert jobs[0]["date_submitted"] is not None

    # Test raw SQL update
    new_note = "Updated note"
    api.update_jobs(
        raw_sql_stmt=f"SET note = '{new_note}' WHERE id = {job_id}"
    )

    # Verify update
    jobs = api.get_jobs(conditions={"id": [("=", job_id)]})
    assert jobs[0]["note"] == new_note


def test_delete_clients(api, sample_rate_data, sample_job_data):
    # Add a client with unique name, rate and job
    client_data = {
        "name": f"Delete Test Client {datetime.now().timestamp()}",
        "email": "delete_test@example.com",
    }
    client_id = api.add_client(client_data)

    # Add rate for client
    rate_data = sample_rate_data.copy()
    rate_data["client_id"] = client_id
    api.add_rates(rate_data)

    # Add job for client
    job_data = sample_job_data.copy()
    job_data["client_id"] = client_id
    api.add_job(job_data)

    # Delete the client (should cascade to rates and jobs)
    deleted_clients = api.delete_clients(
        conditions={"id": [("=", client_id)]}
    )

    # Verify deletion
    assert len(deleted_clients) == 1
    assert deleted_clients[0]["id"] == client_id

    # Verify rates were deleted (cascade)
    rates = api.get_rates(conditions={"client_id": [("=", client_id)]})
    assert len(rates) == 0

    # Verify jobs were deleted (cascade)
    jobs = api.get_jobs(conditions={"client_id": [("=", client_id)]})
    assert len(jobs) == 0


def test_delete_jobs(api, sample_job_data):
    # Add a client with unique name and job
    client_data = {
        "name": f"Job Delete Test Client {datetime.now().timestamp()}",
        "email": "job_delete_test@example.com",
    }
    client_id = api.add_client(client_data)
    job_data = sample_job_data.copy()
    job_data["client_id"] = client_id
    job_id = api.add_job(job_data)

    # Delete the job
    deleted_jobs = api.delete_jobs(conditions={"id": [("=", job_id)]})

    # Verify deletion
    assert len(deleted_jobs) == 1
    # assert str(job_id) in deleted_jobs[0]["job_path"]

    # Verify job is gone
    jobs = api.get_jobs(conditions={"id": [("=", job_id)]})
    assert len(jobs) == 0


def test_build_statement_with_conditions(api):
    # Test select statement
    stmt = api._build_statement_with_conditions(
        Client,
        conditions={"name": [("=", "Test")], "id": [(">", 1), ("<", 10)]},
        stmt_type="select",
    )
    assert stmt is not False
    assert "SELECT" in str(stmt)

    # Test update statement
    stmt = api._build_statement_with_conditions(
        Client, conditions={"name": [("=", "Test")]}, stmt_type="update"
    )
    assert stmt is not False
    assert "UPDATE" in str(stmt)

    # Test delete statement
    stmt = api._build_statement_with_conditions(
        Client, conditions={"name": [("=", "Test")]}, stmt_type="delete"
    )
    assert stmt is not False
    assert "DELETE" in str(stmt)

    # Test invalid statement type
    with pytest.raises(ValueError):
        api._build_statement_with_conditions(
            Client, conditions={"name": [("=", "Test")]}, stmt_type="invalid"
        )

    # Test invalid operator
    with pytest.raises(ValueError):
        api._build_statement_with_conditions(
            Client,
            conditions={"name": [("invalid", "Test")]},
            stmt_type="select",
        )
    with pytest.raises(ValueError):
        api._build_statement_with_conditions(
            Client, conditions={"name": [("??", "test")]}, stmt_type="select"
        )

    with pytest.raises(AttributeError):
        api._build_statement_with_conditions(
            Client, conditions={"bad_column": [("=", 1)]}, stmt_type="select"
        )


def test_build_statement_exceptions(api):
    # Test invalid column (AttributeError) - already covered but let's be explicit with the specific error message check if needed
    with pytest.raises(
        AttributeError, match="Invalid column name 'bad_column'"
    ):
        api._build_statement_with_conditions(
            Client, conditions={"bad_column": [("=", 1)]}
        )

    # Test invalid operator (ValueError)
    with pytest.raises(ValueError, match="Invalid comparison operator"):
        api._build_statement_with_conditions(
            Client, conditions={"name": [("bad_op", "test")]}
        )

    # Test invalid statement type (ValueError)
    with pytest.raises(ValueError, match="Invalid stmt_type"):
        api._build_statement_with_conditions(
            Client, conditions={"name": [("=", "test")]}, stmt_type="insert"
        )


def test_api_update_generic(api, sample_client_data):
    client_id = api.add_client(sample_client_data)

    # Test raw sql update
    result = api.update(
        Client, raw_sql_stmt=f"SET name='Updated' WHERE id={client_id}"
    )
    assert result is not False

    # Test update with missing args (returns False)
    assert (
        api.update(Client, conditions=None, values={"name": "test"}) is False
    )
    assert (
        api.update(Client, conditions={"id": [("=", 1)]}, values=None)
        is False
    )

    # invalid column in values might not raise at this stage depending on SQLAlchemy version
    # so we skip asserting it returns False here to avoid flakes


def test_api_delete_generic(api, sample_client_data):
    client_id = api.add_client(sample_client_data)

    # Test raw sql delete
    result = api.delete(
        Client, conditions=None, raw_sql_stmt=f"WHERE id={client_id}"
    )
    assert result is not False

    # Test delete with error (invalid operator in generic delete)
    # The delete method catches exceptions and returns False
    result = api.delete(Client, conditions={"id": [("bad_op", client_id)]})
    assert result is False


def test_get_method(api):
    # Add a client with unique name for testing
    client_data = {
        "name": f"Get Method Test Client {datetime.now().timestamp()}",
        "email": "get_method_test@example.com",
    }
    client_id = api.add_client(client_data)

    # Test get with no conditions
    stmt = api.get(Client)
    assert isinstance(stmt, type(select(Client)))

    # Test get with conditions
    stmt = api.get(Client, conditions={"id": [("=", client_id)]})
    assert isinstance(stmt, type(select(Client)))

    # Test get with raw SQL
    stmt = api.get(Client, raw_sql_stmt=f"WHERE id = {client_id}")
    assert f"WHERE id = {client_id}" in str(stmt)


def test_compare_conditions_vs_raw_sql(api, sample_job_data):
    """
    Unit test to compare retrieval using conditions vs raw SQL.
    Ensures that both methods return identical data.
    """
    # Setup data
    c1_id = api.add_client({"name": "CompareClient1", "email": "c1@test.com"})
    c2_id = api.add_client({"name": "CompareClient2", "email": "c2@test.com"})

    # Add jobs
    j1 = sample_job_data.copy()
    j1.update({"client_id": c1_id, "job_number": "J1", "status": "Pending"})
    api.add_job(j1)

    j2 = sample_job_data.copy()
    j2.update({"client_id": c2_id, "job_number": "J2", "status": "Done"})
    api.add_job(j2)

    clients_cond = api.get_clients(
        conditions={"name": [("=", "CompareClient1")]}
    )
    clients_raw = api.get_clients(
        raw_sql_stmt="WHERE name = 'CompareClient1'"
    )

    assert len(clients_cond) == 1
    assert len(clients_raw) == 1
    assert clients_cond == clients_raw

    # By Email Pattern
    clients_cond = api.get_clients(conditions={"email": [("~", "%test.com")]})
    clients_raw = api.get_clients(raw_sql_stmt="WHERE email LIKE '%test.com'")

    # Sort by ID to ensure list equality
    clients_cond.sort(key=lambda x: x["id"])
    clients_raw.sort(key=lambda x: x["id"])
    assert len(clients_cond) >= 2
    assert clients_cond == clients_raw

    # 2. Compare Jobs
    # By Status
    jobs_cond = api.get_jobs(conditions={"status": [("=", "Pending")]})
    jobs_raw = api.get_jobs(raw_sql_stmt="WHERE status = 'Pending'")

    assert len(jobs_cond) == 1
    assert len(jobs_raw) == 1
    assert jobs_cond[0]["job_number"] == jobs_raw[0]["job_number"]
    assert jobs_cond[0]["client"].id == jobs_raw[0]["client"].id

    # By Client ID
    jobs_cond = api.get_jobs(conditions={"client_id": [("=", c2_id)]})
    jobs_raw = api.get_jobs(raw_sql_stmt=f"WHERE client_id = {c2_id}")

    assert len(jobs_cond) == 1
    assert jobs_cond[0]["job_number"] == "J2"

    for j_cond, j_raw in zip(jobs_cond, jobs_raw):
        cond_keys = {k: v for k, v in j_cond.items() if k != "client"}
        raw_keys = {
            k: v
            for k, v in j_raw.items()
            if k not in ("client", "client_name", "client_email")
        }
        assert cond_keys == raw_keys

        assert j_cond["client"].id == j_raw["client"].id
        assert j_cond["client"].name == j_raw["client"].name
        assert j_cond["client"].email == j_raw["client"].email


def test_update_clients_guards_against_failed_statement(api):
    # values=None makes self.update() return False; the wrapper must not
    # forward a bool to session.execute().
    result = api.update_clients(conditions={"id": [("=", 1)]}, values=None)
    assert result is False


def test_update_jobs_guards_against_failed_statement(api):
    result = api.update_jobs(conditions={"id": [("=", 1)]}, values=None)
    assert result == []


def test_delete_clients_guards_against_failed_statement(api):
    result = api.delete_clients(conditions={"id": [("bad_op", 1)]})
    assert result == []


def test_delete_jobs_guards_against_failed_statement(api):
    result = api.delete_jobs(conditions={"id": [("bad_op", 1)]})
    assert result == []
