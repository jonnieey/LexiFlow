from sqlalchemy import create_engine, event

from .models import Base


class Database:
    def __init__(self, db_file: str = ":memory:"):
        self.db_file = db_file

        self.engine = create_engine(f"sqlite:///{db_file}")

        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record: str):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def init_db(self):
        Base.metadata.create_all(self.engine)
        self._backfill_job_columns()

    def _backfill_job_columns(self):
        """Add columns to an existing jobs table that predates them.

        create_all() only creates missing tables, it never alters an
        already-existing one, so a jobs table created before these columns
        existed needs them added explicitly. Safe to call repeatedly.
        """
        new_columns = {
            "provider": "TEXT",
            "external_job_id": "TEXT",
            "transcription_status": "TEXT",
            "transcription_last_polled_at": "TEXT",
            "transcription_last_error": "TEXT",
        }
        with self.engine.connect() as conn:
            existing = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(jobs)")
            }
            for column, col_type in new_columns.items():
                if column not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE jobs ADD COLUMN {column} {col_type}"
                    )
            conn.commit()
