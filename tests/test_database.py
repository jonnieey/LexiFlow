import os

import pytest
from sqlalchemy import inspect, text

from lexiflow.database import Database


# Test models needed for testing (simplified)
class TestDatabase:
    @pytest.fixture
    def memory_db(self):
        """Fixture for in-memory database"""
        db = Database(":memory:")
        db.init_db()
        return db

    @pytest.fixture
    def file_db(self, tmp_path):
        """Fixture for file-based database with temporary path"""
        db_file = tmp_path / "test.db"
        db = Database(str(db_file))
        db.init_db()
        yield db
        # Cleanup
        if os.path.exists(db_file):
            os.unlink(db_file)

    def test_init_memory_db(self, memory_db):
        """Test initialization with in-memory database"""
        assert memory_db.db_file == ":memory:"
        assert memory_db.engine is not None

        # Verify tables are created
        inspector = inspect(memory_db.engine)
        assert "clients" in inspector.get_table_names()

    def test_init_file_db(self, file_db, tmp_path):
        """Test initialization with file-based database"""
        db_file = tmp_path / "test.db"
        assert str(db_file) == file_db.db_file
        assert os.path.exists(db_file)
        assert file_db.engine is not None

        # Verify tables are created
        inspector = inspect(file_db.engine)
        assert "clients" in inspector.get_table_names()

    def test_foreign_keys_enabled(self, memory_db):
        """Test that foreign key constraints are enabled"""
        with memory_db.engine.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys")).fetchone()
            assert result[0] == 1  # Should be enabled

    def test_init_db_idempotency(self, memory_db):
        """Test that calling init_db multiple times doesn't fail"""
        # First call done in fixture
        # Second call
        memory_db.init_db()

        inspector = inspect(memory_db.engine)
        assert "clients" in inspector.get_table_names()
        # Verify data persists (if any were added) - technically init_db doesn't clear data, just creates tables if missing

    def test_init_db_backfills_new_job_columns_on_legacy_db(self, tmp_path):
        """create_all() only creates missing tables, not missing columns on an
        already-existing table. A DB file created before provider/
        external_job_id/transcription_status existed must still get them."""
        db_file = tmp_path / "legacy.db"

        import sqlite3

        conn = sqlite3.connect(str(db_file))
        conn.execute(
            """
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY,
                client_id INTEGER NOT NULL,
                date_received TEXT NOT NULL,
                job_number TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                date_due TEXT NOT NULL,
                total_quantity REAL NOT NULL,
                quantity REAL NOT NULL,
                job_rate REAL NOT NULL,
                date_submitted TEXT,
                amount REAL NOT NULL,
                amount_paid REAL NOT NULL DEFAULT 0.0,
                job_path TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO clients (id, name, email) VALUES (1, 'Existing', 'e@x.com')"
        )
        conn.execute(
            """
            INSERT INTO jobs (
                id, client_id, date_received, job_number, job_type, status,
                date_due, total_quantity, quantity, job_rate, amount, job_path
            ) VALUES (1, 1, '2023-01-01', 'J1', 'Normal', 'Pending',
                '2023-01-10', 10.0, 10.0, 0.4, 4.0, '/path')
            """
        )
        conn.commit()
        conn.close()

        db = Database(str(db_file))
        db.init_db()

        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("jobs")}
        assert "provider" in columns
        assert "external_job_id" in columns
        assert "transcription_status" in columns
        assert "transcription_last_polled_at" in columns
        assert "transcription_last_error" in columns

        # Existing row survives the backfill with the new columns NULL.
        with db.engine.connect() as conn2:
            row = conn2.execute(
                text("SELECT job_number, provider FROM jobs WHERE id = 1")
            ).fetchone()
        assert row[0] == "J1"
        assert row[1] is None

    def test_init_db_column_backfill_is_idempotent(self, tmp_path):
        db_file = tmp_path / "test.db"
        db = Database(str(db_file))
        db.init_db()
        db.init_db()  # must not raise "duplicate column name"

        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("jobs")}
        assert "provider" in columns

    def test_invalid_db_path(self):
        """Test initialization with invalid path (might raise error depending on sqlalchemy)"""
        # SQLite usually creates file if possible, but if directory doesn't exist?
        # create_engine doesn't validate path immediately, but connection might fail.
        # However, this depends on OS.
