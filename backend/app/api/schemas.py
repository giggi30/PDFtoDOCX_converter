import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.jobs import JobPhase, JobStatus
from app.quality.models import QualityMetrics


class ConversionCreated(BaseModel):
    job_id: uuid.UUID
    access_token: str
    status: JobStatus
    expires_at: datetime


class ConversionStatus(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    phase: JobPhase | None
    progress: int
    warnings: list[str]
    error: str | None = None
    expires_at: datetime


class ConversionResult(BaseModel):
    job_id: uuid.UUID
    overall_score: float | None = None
    rating: Literal["excellent", "good", "fair", "poor"] | None = None
    metrics: QualityMetrics | None = None
    differences: list[str] = Field(default_factory=list)
    source_preview_urls: list[str] = Field(default_factory=list)
    result_preview_urls: list[str] = Field(default_factory=list)
    download_available: bool


class DeleteResponse(BaseModel):
    status: Literal["deleted"] = "deleted"


class ErrorResponse(BaseModel):
    detail: str
    code: str
