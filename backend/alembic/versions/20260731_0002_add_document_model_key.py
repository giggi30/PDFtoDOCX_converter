"""add document model artifact key

Revision ID: 20260731_0002
Revises: 20260731_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0002"
down_revision: str | None = "20260731_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversion_jobs",
        sa.Column("document_model_key", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversion_jobs", "document_model_key")
