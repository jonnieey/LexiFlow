"""Add provider tracking columns to jobs

Revision ID: 89e25a4bf754
Revises: 62d1a1352ffe
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "89e25a4bf754"
down_revision: Union[str, Sequence[str], None] = "62d1a1352ffe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("jobs", sa.Column("provider", sa.String(), nullable=True))
    op.add_column(
        "jobs", sa.Column("external_job_id", sa.String(), nullable=True)
    )
    op.add_column(
        "jobs", sa.Column("transcription_status", sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("jobs", "transcription_status")
    op.drop_column("jobs", "external_job_id")
    op.drop_column("jobs", "provider")
