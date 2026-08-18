"""create conversion jobs

Revision ID: 20260731_0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                "EXPIRED",
                name="job_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "phase",
            sa.Enum(
                "VALIDATING",
                "EXTRACTING",
                "ANALYZING_LAYOUT",
                "BUILDING_DOCX",
                "RENDERING",
                "COMPARING",
                name="job_phase",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("result_key", sa.String(length=255), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversion_jobs_expires_at", "conversion_jobs", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_conversion_jobs_expires_at", table_name="conversion_jobs")
    op.drop_table("conversion_jobs")
