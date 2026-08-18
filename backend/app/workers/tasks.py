import json
import uuid
from datetime import UTC, datetime
from typing import cast  # noqa: F401  – kept for potential future use

from app.conversion.docx_builder import document_model_to_docx
from app.conversion.extractor import extract_pdf
from app.conversion.layout_analyzer import analyze_layout
from app.core.config import get_settings
from app.db.repository import ConversionJobRepository
from app.db.session import SessionLocal
from app.domain.jobs import JobPhase, JobStatus
from app.quality.comparator import compare_conversion, extract_docx_text
from app.quality.renderer import RenderedPage, render_docx, render_pdf
from app.services.pdf_validation import validate_pdf
from app.services.storage import LocalTemporaryStorage


def _write_previews(
    storage: LocalTemporaryStorage,
    pages: list[RenderedPage],
    kind: str,
) -> list[str]:
    keys: list[str] = []
    for page in pages:
        key = storage.new_key(f".{kind}-preview-{page.page_number}.png")
        storage.write(key, page.png)
        keys.append(key)
    return keys


def _model_text(document_model: object) -> str:
    from app.conversion.models import DocumentModel

    if not isinstance(document_model, DocumentModel):
        raise TypeError("document_model must be a DocumentModel")
    return "\n".join(
        block.text
        for page in document_model.pages
        for region in page.regions
        for block in region.blocks
    )


def process_conversion(job_id: str) -> None:
    settings = get_settings()
    storage = LocalTemporaryStorage(settings.storage_path)
    with SessionLocal() as session:
        repository = ConversionJobRepository(session)
        job = repository.get(uuid.UUID(job_id))
        if job is None or job.status is not JobStatus.QUEUED:
            return
        try:
            job.transition(JobStatus.PROCESSING, JobPhase.VALIDATING)
            repository.commit()
            source = storage.read(job.source_key)
            validate_pdf(
                source,
                "application/pdf",
                settings.max_upload_bytes,
                settings.max_pdf_pages,
            )

            job.transition(JobStatus.PROCESSING, JobPhase.EXTRACTING)
            repository.commit()
            extracted = extract_pdf(source)

            job.transition(JobStatus.PROCESSING, JobPhase.ANALYZING_LAYOUT)
            repository.commit()
            document_model = analyze_layout(extracted)

            job.transition(JobStatus.PROCESSING, JobPhase.BUILDING_DOCX)
            repository.commit()
            docx_result = document_model_to_docx(
                document_model,
            )
            document_model.warnings = list(docx_result.warnings)

            document_model_key = storage.new_key(".document-model.json")
            storage.write(document_model_key, document_model.model_dump_json(indent=2).encode())
            job.document_model_key = document_model_key
            job.warnings_json = json.dumps(document_model.warnings)
            result_key = storage.new_key(".docx")
            storage.write(result_key, docx_result.content)
            job.result_key = result_key
            repository.commit()

            job.transition(JobStatus.PROCESSING, JobPhase.RENDERING)
            repository.commit()
            source_pages = render_pdf(source, dpi=settings.preview_dpi)
            result_pages = render_docx(
                docx_result.content,
                dpi=settings.preview_dpi,
                libreoffice_binary=settings.libreoffice_binary,
                timeout_seconds=settings.libreoffice_timeout_seconds,
            )
            job.source_preview_keys_json = json.dumps(
                _write_previews(storage, source_pages, "source")
            )
            job.result_preview_keys_json = json.dumps(
                _write_previews(storage, result_pages, "result")
            )
            repository.commit()

            job.transition(JobStatus.PROCESSING, JobPhase.COMPARING)
            repository.commit()
            quality_report = compare_conversion(
                source_pages,
                result_pages,
                source_text=_model_text(document_model),
                result_text=extract_docx_text(docx_result.content),
            )
            job.quality_report_json = quality_report.model_dump_json()
            repository.commit()

            job.transition(JobStatus.COMPLETED)
            repository.commit()
        except Exception:
            session.rollback()
            current = repository.get(uuid.UUID(job_id))
            if current is not None and current.status not in {
                JobStatus.COMPLETED,
                JobStatus.CANCELLED,
                JobStatus.EXPIRED,
            }:
                current.error_code = "CONVERSION_FAILED"
                current.transition(JobStatus.FAILED)
                repository.commit()
            raise


def cleanup_expired_jobs() -> int:
    """Expire due jobs and remove their artifacts; safe to call repeatedly."""
    settings = get_settings()
    storage = LocalTemporaryStorage(settings.storage_path)
    cleaned = 0
    with SessionLocal() as session:
        repository = ConversionJobRepository(session)
        for job in repository.expired_before(datetime.now(UTC)):
            storage.delete(job.source_key)
            storage.delete(job.result_key)
            storage.delete(job.document_model_key)
            for key in json.loads(job.source_preview_keys_json):
                storage.delete(key)
            for key in json.loads(job.result_preview_keys_json):
                storage.delete(key)
            if job.status is not JobStatus.EXPIRED:
                job.transition(JobStatus.EXPIRED)
            cleaned += 1
        repository.commit()
    return cleaned
