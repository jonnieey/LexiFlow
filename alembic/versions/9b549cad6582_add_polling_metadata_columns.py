"""Add transcription polling metadata columns to jobs

Revision ID: 9b549cad6582
Revises: 89e25a4bf754
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b549cad6582"
down_revision: Union[str, Sequence[str], None] = "89e25a4bf754"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "jobs",
        sa.Column("transcription_last_polled_at", sa.String(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("transcription_last_error", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("jobs", "transcription_last_error")
    op.drop_column("jobs", "transcription_last_polled_at")
