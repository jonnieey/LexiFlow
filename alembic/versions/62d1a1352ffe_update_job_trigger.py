"""Update job trigger

Revision ID: 62d1a1352ffe
Revises: 14b108a1a069
Create Date: 2025-10-06 14:15:18.655276

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "62d1a1352ffe"
down_revision: Union[str, Sequence[str], None] = "14b108a1a069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS update_amount
        AFTER UPDATE OF job_rate, quantity ON Jobs
        BEGIN
            UPDATE Jobs
            SET amount = CEIL((NEW.quantity * NEW.job_rate) / 0.5) * 0.5
            WHERE id = NEW.id;
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS update_date
            AFTER UPDATE OF status ON Jobs
        BEGIN
            UPDATE Jobs
            SET
                date_submitted = CASE
                    WHEN NEW.status = 'Pending' THEN NULL
                    WHEN NEW.status = 'Done' AND NEW.date_submitted IS NULL THEN DATE("NOW", 'localtime')
                    ELSE date_submitted
                END
                WHERE id = NEW.id;
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS update_status
            AFTER UPDATE OF date_submitted ON Jobs
        BEGIN
            UPDATE Jobs
            SET
                status = CASE
                    WHEN NEW.date_submitted IS NULL THEN 'Pending'
                    WHEN NEW.date_submitted IS '' THEN 'Pending'
                    WHEN DATE(NEW.date_submitted) IS NOT NULL THEN 'Done'
                    ELSE status
                END
                WHERE id = NEW.id;
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS limit_amounts_paid
            AFTER UPDATE OF amount_paid ON Jobs
        BEGIN
            UPDATE Jobs
            SET
                amount_paid = (
                    CASE
                        WHEN NEW.amount_paid > Jobs.amount THEN Jobs.amount
                        ELSE NEW.amount_paid
                    END
                )
                WHERE Jobs.id = New.id;
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS update_job_rate
        AFTER UPDATE OF job_type ON Jobs
        BEGIN
            UPDATE Jobs
                SET job_rate =
                    CASE
                        WHEN LOWER(NEW.job_type) = 'normal' THEN (SELECT normal FROM Rates WHERE Rates.id = NEW.client_id)
                        WHEN LOWER(NEW.job_type) = 'expedite' THEN (SELECT expedite FROM Rates WHERE Rates.id = NEW.client_id)
                        WHEN LOWER(NEW.job_type) = 'interpreted' THEN (SELECT interpreted FROM Rates WHERE Rates.id = NEW.client_id)
                        ELSE NEW.job_rate
                    END
            WHERE id = NEW.id;
        END;
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS update_client_job_rates
            AFTER UPDATE OF client_id ON Jobs
        BEGIN
            UPDATE Jobs
                SET job_rate = CASE
                    WHEN LOWER(job_type) = 'normal' THEN (SELECT normal FROM Rates WHERE Rates.id = New.client_id)
                    WHEN LOWER(job_type) = 'expedite' THEN (SELECT expedite FROM Rates WHERE Rates.id = New.client_id)
                    WHEN LOWER(job_type) = 'interpreted' THEN (SELECT interpreted FROM Rates WHERE Rates.id = New.client_id)
                    ELSE job_rate
                END
            WHERE id = NEW.id;
        END;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(""" DROP TRIGGER IF EXISTS update_amount; """)
    op.execute(""" DROP TRIGGER IF EXISTS update_date; """)
    op.execute(""" DROP TRIGGER IF EXISTS update_status; """)
    op.execute(""" DROP TRIGGER IF EXISTS limit_amounts_paid; """)
    op.execute(""" DROP TRIGGER IF EXISTS update_job_rate; """)
    op.execute(""" DROP TRIGGER IF EXISTS update_client_job_rates; """)
