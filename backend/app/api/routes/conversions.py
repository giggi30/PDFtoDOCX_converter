import json
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import AuthorizedJob
from app.api.schemas import (
    ConversionCreated,
    ConversionResult,
    ConversionStatus,
    DeleteResponse,
)
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_access_token
from app.db.models import ConversionJob
from app.db.repository import ConversionJobRepository
from app.db.session import get_db
from app.domain.jobs import JobStatus, progress_for
from app.quality.models import QualityReport
from app.services.pdf_validation import InvalidPdfError, validate_pdf
from app.services.queue import JobDispatcher, get_dispatcher
from app.services.storage import LocalTemporaryStorage

router = APIRouter(prefix="/conversions", tags=["conversions"])


def _storage(settings: Settings) -> LocalTemporaryStorage:
    return LocalTemporaryStorage(settings.storage_path)


def _preview_keys(job: ConversionJob, kind: Literal["source", "result"]) -> list[str]:
    value = job.source_preview_keys_json if kind == "source" else job.result_preview_keys_json
    parsed = json.loads(value)
    return [item for item in parsed if isinstance(item, str)]


@router.post("", response_model=ConversionCreated, status_code=status.HTTP_202_ACCEPTED)
def create_conversion(
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    dispatcher: Annotated[JobDispatcher, Depends(get_dispatcher)],
) -> ConversionCreated:
    content = file.file.read(settings.max_upload_bytes + 1)
    try:
        validate_pdf(content, file.content_type, settings.max_upload_bytes, settings.max_pdf_pages)
    except InvalidPdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    storage = _storage(settings)
    source_key = storage.new_key(".pdf")
    storage.write(source_key, content)
    access_token = create_access_token()
    job = ConversionJob(
        token_hash=hash_access_token(access_token, settings.token_pepper),
        mode="standard",
        source_key=source_key,
        original_filename=(file.filename or "document.pdf")[:255],
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.job_ttl_minutes),
    )
    repository = ConversionJobRepository(db)
    repository.add(job)
    try:
        repository.commit()
        dispatcher.enqueue(job.id)
    except Exception as exc:
        db.rollback()
        if job.id is not None:
            # Best-effort cleanup when DB commit succeeded but queue enqueue failed.
            try:
                persisted_job = repository.get(job.id)
            except Exception:
                persisted_job = None
            if persisted_job is not None:
                try:
                    repository.delete(persisted_job)
                    repository.commit()
                except Exception:
                    db.rollback()
        with suppress(Exception):
            storage.delete(source_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversion service is temporarily unavailable",
        ) from exc
    return ConversionCreated(
        job_id=job.id,
        access_token=access_token,
        status=job.status,
        expires_at=job.expires_at,
    )


@router.get("/{job_id}", response_model=ConversionStatus)
def get_conversion(job_id: uuid.UUID, job: AuthorizedJob) -> ConversionStatus:
    del job_id
    return ConversionStatus(
        job_id=job.id,
        status=job.status,
        phase=job.phase,
        progress=progress_for(job.status, job.phase),
        warnings=json.loads(job.warnings_json),
        error=job.error_code,
        expires_at=job.expires_at,
    )


@router.get("/{job_id}/result", response_model=ConversionResult)
def get_conversion_result(job_id: uuid.UUID, job: AuthorizedJob) -> ConversionResult:
    del job_id
    if job.status is not JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversion is not completed",
        )
    quality = (
        QualityReport.model_validate_json(job.quality_report_json)
        if job.quality_report_json
        else None
    )
    source_keys = _preview_keys(job, "source")
    result_keys = _preview_keys(job, "result")
    return ConversionResult(
        job_id=job.id,
        overall_score=quality.overall_score if quality else None,
        rating=quality.rating if quality else None,
        metrics=quality.metrics if quality else None,
        differences=quality.differences if quality else [],
        source_preview_urls=[
            f"/api/v1/conversions/{job.id}/preview/source/{index}"
            for index in range(1, len(source_keys) + 1)
        ],
        result_preview_urls=[
            f"/api/v1/conversions/{job.id}/preview/result/{index}"
            for index in range(1, len(result_keys) + 1)
        ],
        download_available=job.result_key is not None,
    )


@router.get("/{job_id}/preview/{kind}/{page_number}")
def preview_conversion(
    job_id: uuid.UUID,
    kind: Literal["source", "result"],
    page_number: int,
    job: AuthorizedJob,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    del job_id
    if job.status is not JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversion is not completed",
        )
    keys = _preview_keys(job, kind)
    if page_number < 1 or page_number > len(keys):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")
    storage = _storage(settings)
    key = keys[page_number - 1]
    if not storage.exists(key):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Preview artifact is unavailable",
        )
    return FileResponse(storage.path_for(key), media_type="image/png")


@router.get("/{job_id}/download")
def download_conversion(
    job_id: uuid.UUID,
    job: AuthorizedJob,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    del job_id
    if job.status is not JobStatus.COMPLETED or job.result_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversion is not completed",
        )
    storage = _storage(settings)
    if not storage.exists(job.result_key):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Conversion artifact is unavailable",
        )
    output_name = f"{job.id}.docx"
    return FileResponse(
        storage.path_for(job.result_key),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=output_name,
    )


@router.delete("/{job_id}", response_model=DeleteResponse)
def delete_conversion(
    job_id: uuid.UUID,
    job: AuthorizedJob,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeleteResponse:
    del job_id
    storage = _storage(settings)
    storage.delete(job.source_key)
    storage.delete(job.result_key)
    storage.delete(job.document_model_key)
    for kind in ("source", "result"):
        for key in _preview_keys(job, kind):
            storage.delete(key)
    repository = ConversionJobRepository(db)
    repository.delete(job)
    repository.commit()
    return DeleteResponse()
