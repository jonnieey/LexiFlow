import logging
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, Union

from sqlalchemy import and_
from sqlalchemy import delete as sql_delete
from sqlalchemy import select, text
from sqlalchemy.engine.row import RowMapping
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.dml import Delete, Update
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.selectable import Select

from lexiflow.database import Database
from lexiflow.models import Client, Job, Rate

DB_FILE_NAME = "transcriptor.db"

logger = logging.getLogger(__name__)


class API:
    def __init__(self, base_dir: Path | str) -> None:
        """Initializes the API with a base directory and sets up the database connection.
        Args:
            base_dir (str): The base directory where data will be stored.
        """
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        self.base_dir = base_dir
        self.db = Database(db_file=f"{base_dir}/{DB_FILE_NAME}")
        self._session_factory = sessionmaker(
            self.db.engine, expire_on_commit=False
        )
        self.db.init_db()

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def add(self, table: object, data: dict) -> int:
        """Adds a new record to the specified table.

        Args:
            table (sqlalchemy.ext.declarative.api.DeclarativeMeta): The SQLAlchemy table class to add the record to.
            data (dict): A dictionary containing the data for the new record.  Keys should correspond to column names in the table.

        Returns:
            int: The ID of the newly created record.
        """
        obj = table(**data)  # type: ignore
        with self.session_scope() as session:
            session.add(obj)
            # No need to commit here, session_scope handles it
            session.flush()
            return obj.id

    def add_client(self, client_dict: dict) -> int:
        """Adds a new client to the database.

        Args:
            client_dict (dict): A dictionary containing the client's information.

        Returns:
            int: The ID of the newly created client record.

        """
        return self.add(Client, client_dict)

    def add_rates(self, rates_dict: dict) -> int:
        """Adds rates to the database.

        Args:
            rates_dict (dict): A dictionary where keys are rate identifiers and values
                are dictionaries containing rate information

        Returns:
            int: The ID of the newly created rates record.
        """
        return self.add(Rate, rates_dict)

    def add_job(self, job_dict: dict) -> int:
        """Adds a single job to the database.

        Args:
            job_dict (dict): A dictionary containing the job details.

        Returns:
            int: The ID of the newly added job.
        """
        return self.add(Job, job_dict)

    def add_jobs(self, jobs: list[dict]) -> None:
        """Adds multiple jobs to the database in a single session.

        Args:
            jobs (list[dict]): A list of dictionaries, where each dictionary
                represents a job and contains the job details.

        Returns:
            None
        """
        job_objects = [Job(**job_dict) for job_dict in jobs]
        with self.session_scope() as session:
            session.add_all(job_objects)

    def _build_statement_with_conditions(
        self,
        table: Union[Type[Rate], Type[Job], Type[Client]],
        conditions: Optional[
            Dict[
                str,
                Union[
                    List[
                        Union[
                            Tuple[str, str], Tuple[str, int], Tuple[str, date]
                        ]
                    ],
                    List[Tuple[str, int]],
                    List[Tuple[str, str]],
                    List[Union[Tuple[str, str], Tuple[str, int]]],
                ],
            ]
        ] = None,
        stmt_type: str = "select",
    ) -> Union[Select, Update, Delete, bool]:
        """Builds a SQL statement with conditions.

        Args:
            table (sqlalchemy.Table): The SQLAlchemy table object to build
              the statement for.
            conditions (dict[str, list[tuple[str, typing.Any]]]): A dictionary
            where keys are column names and values are lists of tuples.
              Each tuple in the list represents a condition for that column,
              with the first element being the comparison operator and the
              second element being the value to compare against.
                Example: `{"column_name": [("=", "value"), (">", 10)]}`
            stmt_type (str, optional): The type of SQL statement to build.
              Must be one of "select", "update", or "delete". Defaults to "select".

        Returns:
            sqlalchemy.sql.expression.Select or sqlalchemy.sql.expression.Update
              or sqlalchemy.sql.expression.Delete or False:

        Raises:
            ValueError: If `stmt_type` is not one of "select", "update", or "delete".
            ValueError: If an invalid comparison operator is used in the `conditions`.

        Example:
            To build a SELECT statement:
            ```python
            conditions = {"age": [(">=", 18), ("<", 65)], "city": [("=", "New York")]}
            statement = _build_statement_with_conditions(table, conditions)
            # statement will be a SQLAlchemy select object equivalent to:
            # SELECT * FROM my_table WHERE age >= 18 AND age < 65 AND city = "New York"
            ```

            To build an UPDATE statement:
            ```python
            table = my_table  # SQLAlchemy table object
            conditions = {"age": [(">=", 18), ("<", 65)], "city": [("=", "New York")]}
            statement = _build_statement_with_conditions(table, conditions, stmt_type="update")
            # statement will be a SQLAlchemy update object equivalent to:
            # UPDATE my_table SET ... WHERE age >= 18 AND age < 65 AND city = "New York"
            ```

            To build a DELETE statement:
            ```python
            table = my_table  # SQLAlchemy table object
            conditions = {"age": [(">=", 18), ("<", 65)], "city": [("=", "New York")]}
            statement = _build_statement_with_conditions(table, conditions, stmt_type="delete")
            # statement will be a SQLAlchemy delete object equivalent to:
            # DELETE FROM my_table WHERE age >= 18 AND age < 65 AND city = "New York"
            ```
        """
        if not conditions:
            return False

        if stmt_type == "select":
            stmt = select(table)
        elif stmt_type == "update":
            stmt = table.__table__.update()  # type: ignore
        elif stmt_type == "delete":
            stmt = sql_delete(table)  # type: ignore
        else:
            raise ValueError(
                "Invalid stmt_type.  Must be select, update, or delete"
            )

        try:
            for column, conditions_list in conditions.items():

                try:
                    column_attribute = getattr(table, column)
                except AttributeError as e:
                    raise AttributeError(
                        f"Invalid column name '{column}' for table {table.__name__}"
                    ) from e

                op_map = {
                    "<=": column_attribute.__le__,
                    ">=": column_attribute.__ge__,
                    "!=": column_attribute.__ne__,
                    "<": column_attribute.__lt__,
                    ">": column_attribute.__gt__,
                    "=": column_attribute.__eq__,
                    "==": column_attribute.__eq__,
                    "~": column_attribute.ilike,
                }
                filters = []
                for comparison_op, comp_value in conditions_list:
                    try:
                        op_func = op_map[comparison_op]
                    except KeyError as e:
                        raise ValueError(
                            f"Invalid comparison operator: '{comparison_op}'. "
                            f"Valid operators are: {', '.join(op_map.keys())}"
                        ) from e
                    filters.append(op_func(comp_value))

                if stmt_type == "select":
                    stmt = stmt.filter(and_(*filters))
                else:
                    stmt = stmt.where(and_(*filters))
            return stmt
        except Exception as e:
            if isinstance(e, (ValueError, AttributeError, KeyError)):
                raise
            # Wrap unexpected errors with more context
            raise Exception(
                f"Error building {stmt_type} statement for table {table.__name__}: {str(e)}"
            ) from e

    def get(
        self,
        table: Union[Type[Rate], Type[Job], Type[Client]],
        conditions: Optional[
            Union[
                Dict[str, List[Tuple[str, str]]],
                Dict[
                    str,
                    List[
                        Union[
                            Tuple[str, str], Tuple[str, int], Tuple[str, date]
                        ]
                    ],
                ],
                Dict[str, List[Tuple[str, int]]],
                Dict[str, List[Union[Tuple[str, str], Tuple[str, int]]]],
            ]
        ] = None,
        raw_sql_stmt: Optional[str] = None,
    ) -> Union[Select, TextClause]:
        if raw_sql_stmt is not None:
            raw_stmt = text(raw_sql_stmt)
            return raw_stmt

        if conditions is None:
            stmt = select(table)
            return stmt

        # type: ignore
        return self._build_statement_with_conditions(
            table, conditions, "select"
        )

    def get_clients(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, Any]]]] = None,
        raw_sql_stmt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch clients based on conditions or raw SQL.

        Returns a list of dicts for consistency with existing view logic.
        """
        with self.session_scope() as session:
            if raw_sql_stmt:
                stmt = text(
                    f"SELECT id, name, email FROM clients {raw_sql_stmt}"
                )
                return [dict(row) for row in session.execute(stmt).mappings()]

            if conditions:
                stmt = self._build_statement_with_conditions(
                    Client, conditions
                )
                clients = session.scalars(stmt).all()
            else:
                stmt = select(Client)
                clients = session.scalars(stmt).all()

            return [
                {"id": c.id, "name": c.name, "email": c.email}
                for c in clients
            ]

    def get_rates(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, Any]]]] = None,
        raw_sql_stmt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch rates with associated client names."""
        with self.session_scope() as session:
            if raw_sql_stmt:
                stmt = text(
                    f"SELECT rates.*, clients.name as client_name "
                    f"FROM rates JOIN clients ON rates.client_id = clients.id {raw_sql_stmt}"
                )
                return [dict(row) for row in session.execute(stmt).mappings()]

            stmt = self.get(Rate, conditions)
            rates = session.scalars(stmt).all()

            return [
                {
                    "id": r.id,
                    "client_name": r.client.name,
                    "normal": r.normal,
                    "expedite": r.expedite,
                    "interpreted": r.interpreted,
                }
                for r in rates
            ]

    def get_jobs(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, Any]]]] = None,
        raw_sql_stmt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs with optional conditions or raw SQL."""
        with self.session_scope() as session:
            if raw_sql_stmt:
                # Note: raw_sql_stmt here is usually expected to be a WHERE clause or similar
                # depending on how it's called in base.py/cli.py
                stmt = text(
                    f"SELECT jobs.*, clients.name as client_name, clients.email as client_email "
                    f"FROM jobs JOIN clients ON jobs.client_id = clients.id {raw_sql_stmt}"
                )
                rows = session.execute(stmt).mappings().all()
                result = []
                for row in rows:
                    job_dict = dict(row)
                    # existing code expects a client object or name in some places
                    job_dict["client"] = Client(
                        id=row["client_id"],
                        name=row["client_name"],
                        email=row["client_email"],
                    )
                    result.append(job_dict)
                return result

            stmt = self.get(Job, conditions)
            jobs = session.scalars(stmt).all()

            # Return a list of dicts that includes the client information
            job_list = []
            for j in jobs:
                j_dict = {
                    column.name: getattr(j, column.name)
                    for column in j.__table__.columns
                }
                j_dict["client"] = j.client
                job_list.append(j_dict)
            return job_list

    def update(
        self,
        table: Union[Type[Rate], Type[Job], Type[Client]],
        conditions: Optional[Dict[str, List[Tuple[str, int]]]] = None,
        values: Optional[Dict[str, str]] = None,
        raw_sql_stmt: None = None,
    ) -> Union[Select[Any], Update, Delete, bool]:
        if raw_sql_stmt is not None:
            raw_sql_stmt = text(
                f"UPDATE {table.__tablename__} {raw_sql_stmt}"
            )
            return raw_sql_stmt

        if not all([conditions, values]):
            return False

        stmt = self._build_statement_with_conditions(
            table, conditions, "update"
        )  # type: ignore
        if stmt is None:
            return False
        try:
            stmt = stmt.values(**values)  # type: ignore
            return stmt

        except Exception as e:
            logger.error(f"Error during update: {e}")
            return False

    def update_clients(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, int]]]] = None,
        values: Optional[Dict[str, str]] = None,
        raw_sql_stmt: None = None,
    ) -> bool:
        stmt = self.update(
            Client,
            conditions=conditions,
            values=values,
            raw_sql_stmt=raw_sql_stmt,
        )
        if stmt is False:
            return False
        with self.session_scope() as session:
            session.execute(stmt)  # type: ignore
            return True

    def update_rates(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, int]]]] = None,
        values: Optional[Dict[str, str]] = None,
        raw_sql_stmt: None = None,
    ):
        stmt = self.update(
            Rate,
            conditions=conditions,
            values=values,
            raw_sql_stmt=raw_sql_stmt,
        )
        if stmt is False:
            return False
        with self.session_scope() as session:
            session.execute(stmt)  # type: ignore
            return True

    def update_jobs(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, int]]]] = None,
        values: Optional[Dict[str, str]] = None,
        raw_sql_stmt: None = None,
    ):
        if raw_sql_stmt is not None:
            raw_sql_stmt = raw_sql_stmt + " RETURNING *;"
        stmt = self.update(
            Job,
            conditions=conditions,
            values=values,
            raw_sql_stmt=raw_sql_stmt,
        )
        if stmt is False:
            return []
        if not raw_sql_stmt:
            stmt = stmt.returning(Job)
        with self.session_scope() as session:
            update_jobs = session.execute(stmt).mappings().all()  # type: ignore
            return update_jobs

    def delete(
        self,
        table: Type[Client],
        conditions: Optional[Dict[str, List[Tuple[str, str]]]],
        raw_sql_stmt: None = None,
    ) -> Delete | bool:
        if raw_sql_stmt is not None:
            raw_sql_stmt = text(
                f"DELETE FROM {table.__tablename__} {raw_sql_stmt}"
            )
            return raw_sql_stmt

        if not conditions:
            return False

        stmt = sql_delete(table)
        try:
            for column, conditions_list in conditions.items():
                column_attribute = getattr(table, column)
                op_map = {
                    "<=": column_attribute.__le__,
                    ">=": column_attribute.__ge__,
                    "!=": column_attribute.__ne__,
                    "<": column_attribute.__lt__,
                    ">": column_attribute.__gt__,
                    "=": column_attribute.__eq__,
                    "==": column_attribute.__eq__,
                    "~": column_attribute.ilike,
                }
                filters = []
                for comparison_op, comp_value in conditions_list:
                    try:
                        filters.append(op_map[comparison_op](comp_value))
                    except KeyError:
                        raise ValueError(
                            f"Invalid comparison operator: {comparison_op}"
                        )
                stmt = stmt.where(and_(*filters))
            return stmt

        except Exception as e:
            logger.error(f"Error during delete: {e}")
            return False

    def delete_clients(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, str]]]] = None,
        raw_sql_stmt: None = None,
    ) -> Sequence[RowMapping]:
        stmt = self.delete(
            Client, conditions=conditions, raw_sql_stmt=raw_sql_stmt
        )
        if stmt is False:
            return []
        stmt = stmt.returning(Client.id, Client.name)  # type: ignore
        with self.session_scope() as session:
            clients = session.execute(stmt).mappings().all()  # type: ignore
            return clients

    def delete_jobs(self, conditions=None, raw_sql_stmt=None):
        stmt = self.delete(
            Job, conditions=conditions, raw_sql_stmt=raw_sql_stmt
        )
        if stmt is False:
            return []
        stmt = stmt.returning(Job.job_path)
        with self.session_scope() as session:
            jobs = session.execute(stmt).mappings().all()
            return jobs


# if __name__ == "__main__":
#     api = API(base_dir=Path(__file__).parent)
#     print(
#         len(
#             api.get_clients(
#                 conditions={
#                     "name": [("~", "%vic%")],
#                     "id": [(">", 1), ("<", 5)],
#                 }
#             )
#         )
#     )
