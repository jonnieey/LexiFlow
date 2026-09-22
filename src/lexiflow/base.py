import asyncio
import csv
import logging
import re
import shutil
import zipfile
from datetime import date, datetime
from itertools import groupby
from operator import itemgetter
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from platformdirs import user_config_dir, user_data_dir
from sqlalchemy.engine.row import RowMapping

from lexiflow.api import API
from lexiflow.backup import Backup
from lexiflow.models import (
    Config,
    Invoice,
    InvoiceLine,
    Profile,
    SummaryInvoice,
    SummaryInvoiceLine,
)
from lexiflow.services import get_service
from lexiflow.utils import (
    TEMPLATE_MAPPING,
    convert,
    extract_table_data_from_docx,
    fetch_rate,
    get_media_files,
    get_version,
    html_to_md,
    htmlstr_to_pdf,
    next_non_existent_file,
    parse_sql_update_query,
    render_invoice,
    render_summary_invoice,
    round_up,
    sc,
)
from lexiflow.utils import str_to_date as std
from lexiflow.utils import to_date_object

APP_NAME = "transcriptor"
CONFIG_FILE_NAME = "config.yaml"

DEFAULT_CONFIG = {
    "base_dir": f"{user_data_dir(APP_NAME)}",
    "date_format": "%Y-%m-%d",
    "invoice_theme": "default",
    "display_currency": "USD",
    "conversion_rate": 0.0,
    "currency_segment": "",
    "currency_receive_country": "",
    "currency_send_country": "us",
    "invoice_currency": "USD",
}

logger = logging.getLogger(__name__)


class Transcriptor:
    def __init__(
        self,
        api: Optional[API] = None,
        config: Optional[Config] = None,
        config_file: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize Transcriptor with optional configuration.

        Args:
            api: Optional API instance to use
            config: Optional Config object
            config_file: Optional path to config file
        """
        self._init_config(config, config_file)
        self._init_profile()
        self._init_api(api)
        self._init_backup()
        self.auto_backup()

    def _init_config(
        self,
        config: Optional[Config],
        config_file: Optional[Union[str, Path]],
    ) -> None:
        """Initialize configuration from file or defaults."""
        self.CONFIG_DIR, self.CONFIG_FILE = self._get_config_paths(
            config_file
        )
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        if config is None:
            if not self._config_file_exists():
                self.config = Config(**DEFAULT_CONFIG)
                self._write_config()
            else:
                self.config = self._load_config()
        else:
            self.config = config
            self._write_config()

        self.base_dir = Path(self.config.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.date_format = self.config.date_format
        self.version = get_version()

    def _get_config_paths(
        self, config_file: Optional[Union[str, Path]]
    ) -> tuple[Path, Path]:
        """Determine config directory and file paths."""
        if config_file is None:
            config_dir = Path(user_config_dir(APP_NAME))
            config_file = config_dir / CONFIG_FILE_NAME
        else:
            config_file = Path(config_file)
            config_dir = config_file.parent
            if not config_dir.exists():
                config_dir.mkdir(parents=True)
        return config_dir, config_file

    def _config_file_exists(self) -> bool:
        """Check if config file exists and is not empty."""
        return (
            self.CONFIG_FILE.exists() and self.CONFIG_FILE.stat().st_size > 0
        )

    def _write_config(self) -> None:
        """Write current config to file."""
        try:
            self.config.write(self.CONFIG_FILE)
        except Exception as e:
            raise RuntimeError(
                f"Failed to write config to {self.CONFIG_FILE}"
            ) from e

    def _load_config(self) -> Config:
        """Load config from file."""
        try:
            return Config.from_yaml(self.CONFIG_FILE)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load config from {self.CONFIG_FILE}"
            ) from e

    def _init_profile(self) -> None:
        """Initialize profile from file or defaults."""
        self.PROFILE_FILE = self.base_dir / "profile.yaml"

        if not self._profile_file_exists():
            self.profile = Profile()
            self._write_profile()
        else:
            self.profile = self._load_profile()

    def _profile_file_exists(self) -> bool:
        """Check if profile file exists and is not empty."""
        return (
            self.PROFILE_FILE.exists()
            and self.PROFILE_FILE.stat().st_size > 0
        )

    def _write_profile(self) -> None:
        """Write current profile to file."""
        try:
            self.profile.write(self.PROFILE_FILE)
        except Exception as e:
            raise RuntimeError(
                f"Failed to write profile to {self.PROFILE_FILE}"
            ) from e

    def _load_profile(self) -> Profile:
        """Load profile from file."""
        try:
            return Profile.from_yaml(self.PROFILE_FILE)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load profile from {self.PROFILE_FILE}"
            ) from e

    def _init_api(self, api: Optional[API]) -> None:
        """Initialize API instance."""
        self.api = api if api is not None else API(base_dir=self.base_dir)

    def _init_backup(self) -> None:
        """Initialize Backup instance."""
        self.backup = Backup(base_dir=self.base_dir)

    def auto_backup(self) -> None:
        """Automatically create a backup if needed."""
        if self.backup.should_auto_backup():
            logger.info("Creating automatic backup...")
            backup_path = self.backup.create_backup()
            logger.info(f"Backup created at: {backup_path}")

    def save_config(self, yaml_file=None):
        if not yaml_file:
            yaml_file = self.CONFIG_FILE
        self.config.write(yaml_file)

    def save_profile(self, yaml_file=None):
        if not yaml_file:
            yaml_file = self.PROFILE_FILE
        self.profile.write(yaml_file)

    def create_client(
        self, name: str, email: str, rates_dict: Optional[dict] = None
    ):
        client_dict = {"name": name, "email": email}
        client_id = self.api.add_client(client_dict)
        if rates_dict is None:
            rates_dict = {
                "normal": 0.4,
                "expedite": 0.6,
                "interpreted": 0.3,
                "client_id": client_id,
            }
        else:
            # Ensure the client_id is always included in rates if provided
            rates_dict["client_id"] = client_id

        self.api.add_rates(rates_dict)
        CLIENT_DIR = self.base_dir / "clients" / sc(name)
        CLIENT_DIR.mkdir(parents=True, exist_ok=True)

        TEMPLATE_DIR = Path(__file__).parent / "templates"
        shutil.copytree(
            TEMPLATE_DIR,
            CLIENT_DIR / "templates",
            dirs_exist_ok=True,
        )

    def create_job_dir(
        self,
        client_name: str,
        job_number: str,
        date_received: str,
        date_due: str,
    ) -> Path:
        """
        Create a job directory

        Arguments:
            client_name: Client name
            job_num: Job number
            date_rec: Date received
            date_due: Date due

        Returns:
            Job directory path object
        """
        date_received_obj = std(date_received, self.date_format)
        date_due_obj = std(date_due, self.date_format)

        job_dir = (
            self.base_dir
            / "clients"
            / sc(client_name)
            / f"{date_received_obj.year}"
            / f"{date_received_obj.strftime('%B')}"
            / f"{date_received_obj.strftime('%d_%a')}_{job_number}_DUE_{date_due_obj.strftime('%d_%a')}"
        )
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    @staticmethod
    def mv_extract_job_file(
        job_file: Path | str, job_dir: Path | str
    ) -> None:
        """
        Move/Extract job file to jobs directory

        Arguments:
            job_file: Path object or path-like string to job file
            job_dir: Path object or path-like string to job directory
        """
        job_file = Path(job_file)
        if zipfile.is_zipfile(job_file):
            try:
                job_dir = Path(job_dir).resolve()
                with zipfile.ZipFile(job_file) as zf:
                    for member in zf.namelist():
                        if member in ("", "/"):
                            # Harmless bare root-directory entry some zip
                            # tools include. pathlib's `job_dir / member`
                            # would discard job_dir entirely for a
                            # leading "/" (treating it as an absolute
                            # path override) and resolve to the
                            # filesystem root, which is not an actual
                            # traversal attempt -- just nothing to check.
                            continue
                        target = (job_dir / member).resolve()
                        if (
                            job_dir not in target.parents
                            and target != job_dir
                        ):
                            raise ValueError(
                                f"Zip member escapes target directory: {member}"
                            )
                    zf.extractall(job_dir)
                job_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Could not extract zip file -> {e}")

        else:
            # shutil.move(job_file, job_dir)
            shutil.copy(job_file, job_dir)

    def select_job_template(self, client: str, template: str) -> Path:
        """
        Select a job template for a task

        Arguments:
            client: Client name
            template: Template name initials

        Returns:
            Path to template file
        """
        client_template_dir = (
            self.base_dir / "clients" / sc(client) / "templates"
        )

        if not client_template_dir.exists():
            jobs_templates_path = Path(__file__).parent / "templates"
            shutil.copytree(
                jobs_templates_path, client_template_dir, dirs_exist_ok=True
            )

        return client_template_dir / TEMPLATE_MAPPING[template]

    def create_job(
        self,
        job_file: str,
        job_info: Dict[str, Any],
        task_callback: Callable[[Path], Dict[str, Any]],
    ):
        if isinstance(job_file, str):
            job_file = job_file.strip("'\"")

        client_query = self.api.get_clients(
            conditions={"id": [("=", job_info["client_id"])]}
        )
        if not client_query:
            logger.error("No client found")
            return
        client = client_query[0]
        job_dir = self.create_job_dir(
            client["name"],
            job_info["job_number"],
            job_info["date_received"],
            job_info["date_due"],
        )
        if Path(job_file).exists():
            self.mv_extract_job_file(job_file, job_dir)
        task_files = get_media_files(job_dir)

        tasks = []
        for task_file in task_files:
            task_info = task_callback(task_file)
            if not task_info:
                continue
            task_info.update(job_info)

            task_template_path = self.select_job_template(
                client["name"], task_info["job_template"]
            )
            task_template_suffix = task_template_path.suffix

            date_due = std(task_info["date_due"], self.date_format)
            job_number = job_info["job_number"]
            task_file_path = next_non_existent_file(
                job_dir
                / f"{job_number} Due {date_due.strftime('%m.%d')}{task_template_suffix}"
            )
            shutil.copy(task_template_path, task_file_path)

            task_rate_obj = self.api.get_rates(
                conditions={"client_id": [("=", client["id"])]}
            )
            task_info["job_rate"] = task_rate_obj[0].get(
                task_info["job_type"].lower()
            )
            task_info["amount"] = round_up(
                float(task_info["job_rate"]) * float(task_info["quantity"])
            )

            task_dict = {
                "client_id": client["id"],
                "date_received": job_info["date_received"],
                "job_number": job_info["job_number"],
                "status": "Pending",
                "amount": task_info["amount"],
                "job_type": task_info["job_type"],
                "date_due": job_info["date_due"],
                "total_quantity": task_info["total_quantity"],
                "quantity": task_info["quantity"],
                "job_rate": task_info["job_rate"],
                "job_path": f"{task_file}",
                "note": task_info["note"],
            }
            tasks.append(task_dict)
        if tasks:
            self.api.add_jobs(tasks)

    def _get_where_clause_from_update_sql(
        self, raw_sql_stmt: str
    ) -> Optional[str]:
        if not raw_sql_stmt:
            return None
        where_idx = raw_sql_stmt.lower().find("where")
        if where_idx != -1:
            where_clause = raw_sql_stmt[where_idx:]
            return re.sub(
                r"\bid\b", "jobs.id", where_clause, flags=re.IGNORECASE
            ).strip()
        return None

    def _get_update_client_name(
        self, conditions: dict, values: dict, raw_sql_stmt: str
    ) -> Optional[str]:
        client_id = None
        if conditions:
            client_id = values.get("client_id")
        elif raw_sql_stmt:
            set_clause, _ = parse_sql_update_query(raw_sql_stmt)
            client_id = set_clause.get("client_id")

        if client_id:
            client_query = self.api.get_clients(
                conditions={"id": [("=", client_id)]}
            )
            if client_query:
                return client_query[0].get("name")
        return None

    def _sync_job_files(
        self,
        job: dict,
        values: dict,
        raw_sql_stmt: str,
        update_client_name: str,
    ) -> Optional[str]:
        keys_to_check = ("date_received", "date_due", "client_id")
        should_update_dir = any(key in values for key in keys_to_check) or (
            raw_sql_stmt and any(key in raw_sql_stmt for key in keys_to_check)
        )

        if not should_update_dir:
            return None

        if not update_client_name:
            client = job.get("client")
            update_client_name = getattr(client, "name", client)

        task_path = Path(job["job_path"])
        old_job_path = task_path.parent
        task_name = task_path.name

        if raw_sql_stmt:
            set_clause, _ = parse_sql_update_query(raw_sql_stmt)
            date_received = set_clause.get(
                "date_received", job.get("date_received")
            )
            date_due = set_clause.get("date_due", job.get("date_due"))
        else:
            date_received = values.get(
                "date_received", job.get("date_received")
            )
            date_due = values.get("date_due", job.get("date_due"))

        new_job_path = self.create_job_dir(
            update_client_name, job["job_number"], date_received, date_due
        )

        if new_job_path != old_job_path:
            try:
                new_job_path.mkdir(exist_ok=True, parents=True)
                for item in old_job_path.iterdir():
                    item.rename(new_job_path / item.name)
                # Only remove if it's empty and different
                if not any(old_job_path.iterdir()):
                    old_job_path.rmdir()
                return str(new_job_path / task_name)
            except Exception as e:
                logger.error(f"Error moving files: {e}")
        return None

    def update_jobs(self, conditions=None, values=None, raw_sql_stmt=None):
        where_clause = self._get_where_clause_from_update_sql(raw_sql_stmt)
        jobs = self.api.get_jobs(
            conditions=conditions, raw_sql_stmt=where_clause
        )

        if not jobs:
            return

        values = values or {}
        update_client_name = self._get_update_client_name(
            conditions, values, raw_sql_stmt
        )

        for job in jobs:
            new_task_path = self._sync_job_files(
                job, values, raw_sql_stmt, update_client_name
            )

            if new_task_path:
                if conditions:
                    values["job_path"] = new_task_path
                elif raw_sql_stmt:
                    # This is tricky with raw SQL, might be better to avoid raw SQL for these updates
                    # but keeping original logic flavor
                    set_idx = raw_sql_stmt.lower().find("set ")
                    if set_idx != -1:
                        raw_sql_stmt = (
                            raw_sql_stmt[:set_idx]
                            + f'set job_path="{new_task_path}", '
                            + raw_sql_stmt[set_idx + len("set ") :]
                        )

            # Re-fetch conditions might be needed if they changed, but using original logic flow
            if conditions:
                self.api.update_jobs(conditions=conditions, values=values)
            elif raw_sql_stmt:
                self.api.update_jobs(raw_sql_stmt=raw_sql_stmt)

    def delete_clients(
        self,
        conditions: Optional[Dict[str, List[Tuple[str, str]]]] = None,
        raw_sql_stmt: None = None,
        purge: bool = False,
    ) -> Sequence[RowMapping]:
        clients = self.api.delete_clients(
            conditions=conditions, raw_sql_stmt=raw_sql_stmt
        )
        if purge:
            for client in clients:
                client_dir = self.base_dir / "clients" / sc(client["name"])
                if client_dir.exists():
                    shutil.rmtree(client_dir)
        return clients

    def delete_jobs(self, conditions=None, raw_sql_stmt=None, purge=False):
        jobs = self.api.delete_jobs(
            conditions=conditions, raw_sql_stmt=raw_sql_stmt
        )
        if purge:
            for job in jobs:
                job_path = Path(job["job_path"])
                shutil.rmtree(job_path.parent)
        return jobs

    def read_invoice_counter(self, invoice_num_counter_file: Path) -> int:
        try:
            with open(invoice_num_counter_file, "r") as file:
                invoice_number = int(file.read())
        except FileNotFoundError:
            invoice_number = 0
        return invoice_number

    def increase_invoice_counter(self, invoice_num_counter_file):
        try:
            with open(invoice_num_counter_file, "r+") as file:
                try:
                    current_invoice_num = int(file.read())
                except ValueError:
                    current_invoice_num = 1
                file.seek(0)
                file.write(f"{current_invoice_num + 1:05}")
                file.truncate()

        except FileNotFoundError:
            invoice_number = 1
            with open(invoice_num_counter_file, "w") as file:
                file.write(f"{invoice_number:05}")

    # def generate_invoice(
    def get_invoice_jobs(
        self,
        client_id: str,
        conditions: Optional[Dict[str, List[Tuple[str, Any]]]] = None,
        raw_sql_stmt: None = None,
    ) -> Tuple[str, Union[int, Any, str, float, None]]:
        if client_id is None:
            logger.error("CLIENT ID CANNOT BE NONE")
            return ("", "")

        if conditions:
            # Use a direct assignment or setdefault to avoid multiple dictionary updates
            conditions.setdefault("client_id", [("=", client_id)])
            conditions["amount_paid"] = [("=", 0)]
        elif raw_sql_stmt:
            try:
                safe_client_id = int(client_id)
            except (TypeError, ValueError):
                logger.error(f"Invalid client_id: {client_id!r}")
                return None
            if "client_id" not in raw_sql_stmt:
                raw_sql_stmt = f"""
                    {raw_sql_stmt} AND client_id = {safe_client_id}
                    AND amount_paid = 0
                    """
            else:
                raw_sql_stmt = f"{raw_sql_stmt} AND amount_paid = 0"

        jobs = self.api.get_jobs(conditions=conditions, raw_sql_stmt=raw_sql_stmt)  # type: ignore
        if not jobs:
            return None
        return jobs

    def get_jobs_by_job_numbers(
        self, client_id: str, job_numbers: List[str]
    ) -> List:
        if not job_numbers:
            return []
        try:
            safe_client_id = int(client_id)
        except (TypeError, ValueError):
            logger.error(f"Invalid client_id: {client_id!r}")
            return []
        # Escape single quotes so a job number can't break out of the SQL
        # string literal it's embedded in below.
        escaped_numbers = [str(n).replace("'", "''") for n in job_numbers]
        placeholders = ", ".join(f"'{n}'" for n in escaped_numbers)
        raw_sql = (
            f"WHERE job_number IN ({placeholders})"
            f" AND client_id = {safe_client_id} AND amount_paid = 0"
        )
        return self.api.get_jobs(raw_sql_stmt=raw_sql) or []

    def _invoice_currency_rate(self):
        """Return (currency_code, rate) for invoice generation.

        Uses config.invoice_currency (default USD). A non-USD currency is
        converted using the display conversion rate; falls back to USD when
        no rate is available.
        """
        currency = getattr(self.config, "invoice_currency", "USD") or "USD"
        currency = currency.upper()
        if currency == "USD":
            return "USD", 1.0

        display = getattr(self.config, "display_currency", "USD") or "USD"
        manual_rate = getattr(self.config, "conversion_rate", 0.0) or 0.0
        # Reuse the configured manual rate when the invoice currency matches
        # the display currency (the rate is defined for the display currency).
        if currency == display.upper() and manual_rate > 0:
            return currency, float(manual_rate)

        rate = fetch_rate(
            currency,
            segment_name=getattr(self.config, "currency_segment", "") or "",
            receive_country=getattr(
                self.config, "currency_receive_country", ""
            )
            or "",
            send_country=getattr(self.config, "currency_send_country", "us")
            or "us",
        )
        if rate is None:
            logger.warning(
                "No conversion rate for %s; falling back to USD", currency
            )
            return "USD", 1.0
        return currency, rate

    def generate_invoice(self, jobs, invoice_theme: Optional[str] = None):
        if not jobs:
            logger.warning("No jobs found")
            return ("", "")

        currency, rate = self._invoice_currency_rate()
        invoice_lines = []
        for job in jobs:
            data = dict(job)
            if currency != "USD":
                data["job_rate"] = convert(job.get("job_rate", 0.0), rate)
            invoice_lines.append(InvoiceLine.parse_obj(data))
        client = jobs[0].get("client")
        client_name = client.name if hasattr(client, "name") else client  # type: ignore

        INVOICE_DIR = self.base_dir / "clients" / sc(client_name) / "invoices"  # type: ignore
        INVOICE_NUM_COUNTER_FILE = INVOICE_DIR / "invoice_number_counter"

        invoice_number = self.read_invoice_counter(INVOICE_NUM_COUNTER_FILE)
        invoice = Invoice(
            profile=self.profile,
            invoice_number=f"{invoice_number + 1:05}",
            client_name=client_name,
            jobs=invoice_lines,
            currency=currency,
        )
        if invoice_theme is None:
            invoice_theme = self.config.invoice_theme
        html = render_invoice(
            invoice=invoice, template_name=f"invoice_{invoice_theme}.html"
        )

        return html, client_name

    def get_summary_invoice_jobs(
        self,
        client_id: str,
        previous_year_cutoff: None = None,
        cutoffs_year: None = None,
        year: None = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        cutoffs = self.load_cutoffs(as_str=True, year=year)

        if client_id is None:
            logger.error("CLIENT ID CANNOT BE NONE")
            return {}

        client_query = self.api.get_clients(
            conditions={"id": [("=", client_id)]}
        )
        if not client_query:
            logger.error(f"No client found with ID {client_id}")
            return {}
        client_name = client_query[0].get("name")

        def merge_months(data):
            data = [d for d in data if d]
            return [
                {
                    "month": month,
                    "job_count": sum(
                        item["job_count"] for item in group_list
                    ),
                    "total": round_up(
                        sum(item["total"] for item in group_list)
                    ),
                }
                for month, group in groupby(data, key=itemgetter("month"))
                for group_list in [list(group)]
            ]

        summary_invoice_list = []
        summary_invoice_dict = {}

        cutoffs_list = list(cutoffs[1:])

        for idx, (cutoff, deposit_date) in enumerate(cutoffs_list, start=1):
            previous_cutoff, cutoff = self.select_cutoff_period(
                idx, year=year
            )
            if previous_cutoff is None:
                previous_cutoff = previous_year_cutoff or date(
                    datetime.now().year, 1, 1
                )

            conditions = {
                "client_id": [("=", client_id)],
                "amount_paid": [(">", 0)],
                "date_submitted": [
                    (">=", previous_cutoff) if previous_cutoff else None,
                    ("<=", cutoff) if cutoff else None,
                ],
            }
            conditions["date_submitted"] = [
                c
                for c in conditions["date_submitted"]  # type: ignore
                if c  # type: ignore
            ]

            jobs_by_month = {}
            jobs = self.api.get_jobs(conditions=conditions)  # type: ignore
            if jobs:
                month_name = std(deposit_date, "%Y-%m-%d").strftime("%B")
                job_count = len(jobs)
                total = round(sum(job["amount_paid"] for job in jobs), 2)
                jobs_by_month["month"] = month_name
                jobs_by_month["job_count"] = job_count or 0
                jobs_by_month["total"] = total or 0
                summary_invoice_list.append(jobs_by_month)

        summary_invoice_list = merge_months(summary_invoice_list)
        if not summary_invoice_list:
            return {}
        summary_invoice_dict[client_name] = summary_invoice_list
        return summary_invoice_dict

        # {'client_name': [{"month": "Jan", "job_count": 0, "total": 0.0}]}

    def generate_summary_invoice(self, summary_invoice_dict):
        client_name = list(summary_invoice_dict.keys())[0]
        jobs_by_month = summary_invoice_dict[client_name]

        currency, rate = self._invoice_currency_rate()
        months_summary_list = []
        for month_info in jobs_by_month:
            if currency != "USD":
                month_info = dict(month_info)
                month_info["total"] = convert(
                    month_info.get("total", 0.0), rate
                )
            months_summary_list.append(
                SummaryInvoiceLine.parse_obj(month_info)
            )

        summary_invoice = SummaryInvoice(
            profile=self.profile,
            client_name=client_name,
            summary_lines=months_summary_list,
            currency=currency,
        )
        html = render_summary_invoice(summary_invoice=summary_invoice)

        return html, client_name

    def html_to_pdf(
        self, html, client_name, output_file=None, summary_invoice=False
    ):
        INVOICE_DIR = self.base_dir / "clients" / sc(client_name) / "invoices"

        if not INVOICE_DIR.exists():
            INVOICE_DIR.mkdir(parents=True, exist_ok=True)

        date_str = date.today().strftime("%Y-%m-%d")
        client_name_sc = sc(client_name)
        file_type = "summary" if summary_invoice else "invoice"

        INVOICE_FILE = (
            INVOICE_DIR / f"{date_str}_{client_name_sc}_{file_type}.pdf"
        )

        htmlstr_to_pdf(html, output_path=INVOICE_FILE)

        if summary_invoice is False:
            INVOICE_NUM_COUNTER_FILE = INVOICE_DIR / "invoice_number_counter"
            self.increase_invoice_counter(INVOICE_NUM_COUNTER_FILE)

    def generate_csv_invoice(self, jobs, client_name):
        if not jobs:
            logger.warning("No jobs found")
            return

        INVOICE_DIR = self.base_dir / "clients" / sc(client_name) / "invoices"
        CSV_DIR = INVOICE_DIR / "csv"
        CSV_DIR.mkdir(parents=True, exist_ok=True)

        date_str = date.today().strftime("%Y-%m-%d")
        client_name_sc = sc(client_name)
        csv_file_path = CSV_DIR / f"{date_str}_{client_name_sc}_invoice.csv"

        currency, rate = self._invoice_currency_rate()
        invoice_lines = []
        for job in jobs:
            data = dict(job)
            if currency != "USD":
                data["job_rate"] = convert(job.get("job_rate", 0.0), rate)
            invoice_lines.append(InvoiceLine.parse_obj(data))

        with open(csv_file_path, "w", newline="") as csvfile:
            fieldnames = [
                "job_number",
                "job_type",
                "job_rate",
                "quantity",
                "amount",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for line in invoice_lines:
                writer.writerow(
                    {
                        "job_number": line.job_number,
                        "job_type": line.job_type,
                        "job_rate": line.job_rate,
                        "quantity": line.quantity,
                        "amount": line.amount,
                    }
                )
        logger.info(f"CSV invoice generated at: {csv_file_path}")

    def to_md(self, html: str) -> str:
        return html_to_md(html)

    def save_cutoffs(
        self,
        cutoffs: List[Union[List[str], Tuple[date, date]]],
        file_path: Optional[
            Union[Union[str, bytes, PathLike[str], PathLike[bytes]], int]
        ] = None,
        year: Optional[Union[str | int]] = None,
    ):
        CUTOFFS_DIR = self.base_dir / "cutoffs"
        CUTOFFS_DIR.mkdir(parents=True, exist_ok=True)

        year = year or date.today().year

        # Save as cutoffs_{year}.csv
        yearly_file_path = CUTOFFS_DIR / f"cutoffs_{year}.csv"
        with open(yearly_file_path, "w", newline="") as fd:
            writer = csv.writer(fd)
            writer.writerows(cutoffs)

        # Also save as current_cutoffs.csv
        current_file_path = CUTOFFS_DIR / "current_cutoffs.csv"
        shutil.copyfile(yearly_file_path, current_file_path)

    def load_cutoffs(
        self,
        file_path: Optional[
            Union[Union[str, bytes, PathLike[str], PathLike[bytes]], int]
        ] = None,
        date_fmt: str = "%Y-%m-%d",
        as_str: bool = False,
        year=None,
    ) -> Union[List[Union[Tuple[date, ...], List[str]]], Sequence[Any]]:
        CUTOFFS_DIR = self.base_dir / "cutoffs"
        CUTOFFS_DIR.mkdir(parents=True, exist_ok=True)

        if file_path is None:
            if year is None:
                # Try to load from current_cutoffs.csv first
                current_file_path = CUTOFFS_DIR / "current_cutoffs.csv"
                if current_file_path.exists():
                    file_path = current_file_path
                else:
                    # Fall back to current year's cutoffs
                    year = date.today().year
                    file_path = CUTOFFS_DIR / f"cutoffs_{year}.csv"
            else:
                file_path = CUTOFFS_DIR / f"cutoffs_{year}.csv"

        with open(file_path, "r", newline="") as fd:
            cutoff_list: Sequence = list(csv.reader(fd))

        if as_str:
            return cutoff_list

        header, *rows = cutoff_list
        cutoffs = [header] + [to_date_object(row, date_fmt) for row in rows]
        return cutoffs

    def select_cutoff_period(
        self, deposit_date_idx: int, cutoffs=None, year=None
    ) -> Tuple[Union[str, date, None], Union[str, date]]:
        if cutoffs is None:
            cutoff_deposit_pairs = self.load_cutoffs(year=year)[1:]
        else:
            cutoff_deposit_pairs = cutoffs

        deposit_date_idx = max(deposit_date_idx - 1, 0)

        if deposit_date_idx == 0:
            cutoff_date = cutoff_deposit_pairs[0][0]
            previous_cutoff_date = None
            try:
                previous_year = cutoff_date.year - 1
                previous_year_cutoffs = self.load_cutoffs(year=previous_year)[
                    1:
                ]
                if previous_year_cutoffs is not None:
                    previous_cutoff_date = previous_year_cutoffs[-1][0]
            except Exception:
                pass
        else:
            cutoff_date = cutoff_deposit_pairs[deposit_date_idx][0]
            previous_cutoff_date = cutoff_deposit_pairs[deposit_date_idx - 1][
                0
            ]

        return previous_cutoff_date, cutoff_date

    def purge_job_files(
        self,
        jobs: List[dict[str, Any]],
    ):
        for job in jobs:
            job_path = Path(job.get("job_path"))
            if job_path.exists():
                purge_path = (
                    job_path if job_path.is_dir() else job_path.parent
                )
                unwanted_files = list(
                    purge_path.glob("**/*[mwzM][p4aiP][3avp3]")
                )
                for p in unwanted_files:
                    try:
                        p.unlink(missing_ok=True)
                    except OSError as e:
                        logger.error(f"Error deleting file {p}: {e}")

    def _get_transcription_job(self, job_id: int) -> Dict[str, Any]:
        jobs = self.api.get_jobs(conditions={"id": [("=", job_id)]})
        if not jobs:
            raise ValueError(f"No job found with id {job_id}")
        return jobs[0]

    def get_job_directory(self, job_id: int) -> Path:
        """Directory containing a job's files (job_path's parent)."""
        job = self._get_transcription_job(job_id)
        return Path(job["job_path"]).parent

    def get_transcript_path(self, job_id: int) -> Path:
        """Where this job's fetched transcript is/would be written."""
        job = self._get_transcription_job(job_id)
        job_dir = Path(job["job_path"]).parent
        return job_dir / f"{job['job_number']}_transcript.txt"

    async def submit_transcription(
        self,
        job_id: int,
        provider: str,
        additional_vocabulary: Optional[List[str]] = None,
    ) -> str:
        """
        Submit an existing job's media file to an external transcription
        provider, recording provider/external_job_id/transcription_status
        on the job row.

        Returns the provider's external job id.
        """
        job = await asyncio.to_thread(self._get_transcription_job, job_id)
        file_path = Path(job["job_path"])
        if not file_path.exists():
            raise FileNotFoundError(f"Job file not found: {file_path}")

        service = get_service(provider)
        try:
            try:
                external_job_id = await service.submit_job(
                    file_path, additional_vocabulary=additional_vocabulary
                )
            except Exception as e:
                await asyncio.to_thread(
                    self.api.update_jobs,
                    conditions={"id": [("=", job_id)]},
                    values={"transcription_last_error": str(e)},
                )
                raise
        finally:
            await service.close()

        await asyncio.to_thread(
            self.api.update_jobs,
            conditions={"id": [("=", job_id)]},
            values={
                "provider": provider,
                "external_job_id": external_job_id,
                "transcription_status": "in_progress",
                "transcription_last_error": None,
            },
        )
        return external_job_id

    async def poll_transcription_status(self, job_id: int) -> Optional[str]:
        """
        Poll the external provider for this job's current transcription
        status and update the job row.

        Returns the new status, or None if the job has no
        provider/external_job_id set yet, or the poll failed.
        """
        job = await asyncio.to_thread(self._get_transcription_job, job_id)
        provider = job.get("provider")
        external_job_id = job.get("external_job_id")
        if not provider or not external_job_id:
            return None

        service = get_service(provider)
        polled_at = datetime.now().isoformat()
        try:
            try:
                status_info = await service.get_job_status(external_job_id)
            except Exception as e:
                await asyncio.to_thread(
                    self.api.update_jobs,
                    conditions={"id": [("=", job_id)]},
                    values={
                        "transcription_last_polled_at": polled_at,
                        "transcription_last_error": str(e),
                    },
                )
                raise
        finally:
            await service.close()

        if status_info is None:
            await asyncio.to_thread(
                self.api.update_jobs,
                conditions={"id": [("=", job_id)]},
                values={
                    "transcription_last_polled_at": polled_at,
                    "transcription_last_error": (
                        "Provider poll returned no status"
                    ),
                },
            )
            return None

        status = status_info.get("status")
        await asyncio.to_thread(
            self.api.update_jobs,
            conditions={"id": [("=", job_id)]},
            values={
                "transcription_status": status,
                "transcription_last_polled_at": polled_at,
                "transcription_last_error": None,
            },
        )
        return status

    async def fetch_transcript(
        self, job_id: int, metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Fetch the transcript text from the external provider and write it
        to a .txt file in the job's existing directory (same convention
        as task files/invoices). Updates transcription_status to
        "transcribed".

        Returns the path to the written transcript file.
        """
        job = await asyncio.to_thread(self._get_transcription_job, job_id)
        provider = job.get("provider")
        external_job_id = job.get("external_job_id")
        if not provider or not external_job_id:
            raise ValueError(
                f"Job {job_id} has no provider/external_job_id set"
            )

        service = get_service(provider)
        try:
            try:
                transcript_text = await service.get_transcript(
                    external_job_id, metadata=metadata
                )
            except Exception as e:
                await asyncio.to_thread(
                    self.api.update_jobs,
                    conditions={"id": [("=", job_id)]},
                    values={"transcription_last_error": str(e)},
                )
                raise
        finally:
            await service.close()

        transcript_path = self.get_transcript_path(job_id)
        await asyncio.to_thread(
            transcript_path.write_text, transcript_text, encoding="utf-8"
        )

        await asyncio.to_thread(
            self.api.update_jobs,
            conditions={"id": [("=", job_id)]},
            values={
                "transcription_status": "transcribed",
                "transcription_last_error": None,
            },
        )
        return transcript_path


if __name__ == "__main__":
    trans5 = Transcriptor()
