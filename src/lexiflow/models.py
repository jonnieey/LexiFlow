from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, root_validator
from sqlalchemy import DDL, CheckConstraint, ForeignKey, String, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    rate: Mapped["Rate"] = relationship(
        "Rate",
        uselist=False,
        cascade="all, delete-orphan",
        back_populates="client",
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="client", cascade="all, delete-orphan"
    )


class Rate(Base):
    __tablename__ = "rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    normal: Mapped[float] = mapped_column(nullable=False)
    expedite: Mapped[float] = mapped_column(nullable=False)
    interpreted: Mapped[float] = mapped_column(nullable=False)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE")
    )
    client: Mapped[Client] = relationship(
        "Client", back_populates="rate", passive_deletes=True
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE")
    )
    date_received: Mapped[str] = mapped_column(nullable=False)
    job_number: Mapped[str] = mapped_column(nullable=False)
    job_type: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, default="Pending")
    date_due: Mapped[str] = mapped_column(nullable=False)
    total_quantity: Mapped[float] = mapped_column(nullable=False)
    quantity: Mapped[float] = mapped_column(nullable=False)
    job_rate: Mapped[float] = mapped_column(nullable=False)
    date_submitted: Mapped[str] = mapped_column(nullable=True)
    amount: Mapped[float] = mapped_column(nullable=False)
    amount_paid: Mapped[float] = mapped_column(nullable=False, default=0.0)
    job_path: Mapped[str] = mapped_column(nullable=False)
    note: Mapped[str] = mapped_column(nullable=False, default="")
    provider: Mapped[Optional[str]] = mapped_column(nullable=True)
    external_job_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    transcription_status: Mapped[Optional[str]] = mapped_column(nullable=True)
    transcription_last_polled_at: Mapped[Optional[str]] = mapped_column(
        nullable=True
    )
    transcription_last_error: Mapped[Optional[str]] = mapped_column(
        nullable=True
    )
    client: Mapped[Client] = relationship("Client", back_populates="jobs")

    __table_args__ = (
        CheckConstraint(
            "date(date_submitted) >= date(date_received)",
            name="check_date_submitted_not_earlier_than_date_received",
        ),
    )


update_amount_trigger = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS update_amount_on_update
    AFTER UPDATE OF job_rate, quantity ON jobs
    BEGIN
        UPDATE jobs
        SET amount = (CAST((NEW.quantity * NEW.job_rate + 0.49) * 2 AS INTEGER)) / 2.0
        WHERE id = NEW.id;
    END;
    """
)

update_amount_insert_trigger = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS update_amount_on_insert
    AFTER INSERT ON jobs
    BEGIN
        UPDATE jobs
        SET amount = (CAST((NEW.quantity * NEW.job_rate + 0.49) * 2 AS INTEGER)) / 2.0
        WHERE id = NEW.id;
    END;
    """
)

event.listen(
    Job.__table__,
    "after_create",
    update_amount_trigger.execute_if(dialect="sqlite"),
)
event.listen(
    Job.__table__,
    "after_create",
    update_amount_insert_trigger.execute_if(dialect="sqlite"),
)

update_date_trigger = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS update_date_on_update
        AFTER UPDATE OF status ON jobs
    BEGIN
        UPDATE jobs
        SET
            date_submitted = CASE
                WHEN NEW.status = 'Pending' THEN NULL
                WHEN NEW.status = 'Done' AND (NEW.date_submitted IS NULL OR NEW.date_submitted = '') THEN DATE("NOW", 'localtime')
                ELSE date_submitted
            END
            WHERE id = NEW.id;
    END;
    """
)

event.listen(
    Job.__table__,
    "after_create",
    update_date_trigger.execute_if(dialect="sqlite"),
)

update_status_trigger = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS update_status_on_update
        AFTER UPDATE OF date_submitted ON jobs
    BEGIN
        UPDATE jobs
        SET
            status = CASE
                WHEN NEW.date_submitted IS NULL THEN 'Pending'
                WHEN NEW.date_submitted = '' THEN 'Pending'
                ELSE 'Done'
            END
            WHERE id = NEW.id;
    END;
    """
)
event.listen(
    Job.__table__,
    "after_create",
    update_status_trigger.execute_if(dialect="sqlite"),
)
limit_amount_paid_trigger = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS limit_amounts_paid_on_update
        AFTER UPDATE OF amount_paid ON jobs
    BEGIN
        UPDATE jobs
        SET
            amount_paid = (
                CASE
                    WHEN NEW.amount_paid > jobs.amount THEN jobs.amount
                    ELSE NEW.amount_paid
                END
            )
            WHERE jobs.id = New.id;
    END;
    """
)
event.listen(
    Job.__table__,
    "after_create",
    limit_amount_paid_trigger.execute_if(dialect="sqlite"),
)

update_client_job_rates_trigger = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS update_client_job_rates_on_update
        AFTER UPDATE OF client_id ON jobs
    BEGIN
        UPDATE jobs
            SET job_rate = CASE
                WHEN LOWER(job_type) = 'normal' THEN (SELECT normal FROM rates WHERE client_id = New.client_id)
                WHEN LOWER(job_type) = 'expedite' THEN (SELECT expedite FROM rates WHERE client_id = New.client_id)
                WHEN LOWER(job_type) = 'interpreted' THEN (SELECT interpreted FROM rates WHERE client_id = New.client_id)
                ELSE job_rate
            END
        WHERE id = NEW.id;
    END;
    """
)
event.listen(
    Job.__table__,
    "after_create",
    update_client_job_rates_trigger.execute_if(dialect="sqlite"),
)

update_job_rate_trigger = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS update_job_rate_on_update
    AFTER UPDATE OF job_type ON jobs
    BEGIN
        UPDATE jobs
            SET job_rate =
                CASE
                    WHEN LOWER(NEW.job_type) = 'normal' THEN (SELECT normal FROM rates WHERE client_id = NEW.client_id)
                    WHEN LOWER(NEW.job_type) = 'expedite' THEN (SELECT expedite FROM rates WHERE client_id = NEW.client_id)
                    WHEN LOWER(NEW.job_type) = 'interpreted' THEN (SELECT interpreted FROM rates WHERE client_id = NEW.client_id)
                    ELSE NEW.job_rate
                END
        WHERE id = NEW.id;
    END;
    """
)
event.listen(
    Job.__table__,
    "after_create",
    update_job_rate_trigger.execute_if(dialect="sqlite"),
)


class YAMLBase(BaseModel):
    @classmethod
    def from_yaml(cls, yaml_file: Path) -> Any:
        try:
            with open(yaml_file, "r") as file:
                data = yaml.safe_load(file)
            return cls(**data)
        except FileNotFoundError:
            raise
        except yaml.YAMLError:
            raise

    def write(self, yaml_file: Path) -> Any:
        try:
            with open(yaml_file, "w") as file:
                yaml.dump(self.model_dump(), file)
        except FileNotFoundError:
            raise
        except yaml.YAMLError:
            raise
        except Exception:
            raise


class Config(YAMLBase):
    base_dir: str
    date_format: str
    invoice_theme: str
    display_currency: str = "USD"
    conversion_rate: float = 0.0
    currency_segment: str = ""
    currency_receive_country: str = ""
    currency_send_country: str = "us"
    invoice_currency: str = "USD"
    # PDF rendering backend ("auto" = first available)
    pdf_backend: str = "auto"
    # LegatoFlow settings (secrets such as API keys come from env vars only).
    # None = unset in file; Settings falls back to env var, then its default.
    ai_model: Optional[str] = None
    base_url: Optional[str] = None
    notebooklm_storage_path: Optional[str] = None
    notebooklm_notebook_id: Optional[str] = None
    notebooklm_prompt_file: Optional[str] = None
    notebooklm_metadata_keys: Optional[str] = None
    notebooklm_max_metadata_tokens: Optional[int] = None
    file_manager: str = ""
    terminal: str = ""


class Profile(YAMLBase):
    name: str = ""
    area: str = ""
    country: str = ""


class InvoiceLine(BaseModel):
    job_number: str
    job_type: str
    job_rate: float
    quantity: float

    @property
    def amount(self) -> float:
        from lexiflow.utils.media_utils import round_up

        return round_up(self.quantity * self.job_rate)


class Invoice(BaseModel):
    profile: Profile
    client_name: str
    invoice_number: str
    create_date: date = Field(default_factory=date.today)
    due_date: Optional[date] = None
    jobs: List[InvoiceLine]
    currency: str = "USD"

    @root_validator(skip_on_failure=True)
    def calculate_due_date(
        cls,
        values: Dict[str, Optional[Union[date, timedelta]]],
    ) -> Dict[str, Optional[Union[date, timedelta]]]:
        if values["due_date"]:
            return values
        values["due_date"] = values["create_date"] + timedelta(days=7)  # type: ignore
        return values


class SummaryInvoiceLine(BaseModel):
    month: str
    job_count: int
    total: float


class SummaryInvoice(BaseModel):
    profile: Profile
    client_name: str
    create_date: date = Field(default_factory=date.today)
    summary_lines: List[SummaryInvoiceLine]
    currency: str = "USD"
