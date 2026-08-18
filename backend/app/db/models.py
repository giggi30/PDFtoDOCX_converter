import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.jobs import JobPhase, JobStatus, validate_transition


def utc_now() -> datetime:
    return datetime.now(UTC)


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=False), default=JobStatus.QUEUED
    )
    phase: Mapped[JobPhase | None] = mapped_column(
        Enum(JobPhase, name="job_phase", native_enum=False), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    result_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_model_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_preview_keys_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    result_preview_keys_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    quality_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    def transition(self, status: JobStatus, phase: JobPhase | None = None) -> None:
        validate_transition(self.status, self.phase, status, phase)
        self.status = status
        self.phase = phase if status is JobStatus.PROCESSING else None
        self.updated_at = utc_now()
        self.version += 1
