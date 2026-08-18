import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import token_matches
from app.db.models import ConversionJob
from app.db.repository import ConversionJobRepository
from app.db.session import get_db
from app.domain.jobs import JobStatus


def get_authorized_job(
    job_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> ConversionJob:
    repository = ConversionJobRepository(db)
    job = repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversion not found")
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
        )
    if not token_matches(authorization[len(prefix) :], job.token_hash, settings.token_pepper):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access token")
    expires_at = job.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC) and job.status is not JobStatus.EXPIRED:
        job.transition(JobStatus.EXPIRED)
        repository.commit()
    return job


AuthorizedJob = Annotated[ConversionJob, Depends(get_authorized_job)]
