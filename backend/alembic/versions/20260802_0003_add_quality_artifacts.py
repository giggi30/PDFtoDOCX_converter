"""add preview and quality report fields

Revision ID: 20260802_0003
Revises: 20260731_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260802_0003"
down_revision: str | None = "20260731_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversion_jobs",
        sa.Column("source_preview_keys_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "conversion_jobs",
        sa.Column("result_preview_keys_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "conversion_jobs",
        sa.Column("quality_report_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversion_jobs", "quality_report_json")
    op.drop_column("conversion_jobs", "result_preview_keys_json")
    op.drop_column("conversion_jobs", "source_preview_keys_json")
