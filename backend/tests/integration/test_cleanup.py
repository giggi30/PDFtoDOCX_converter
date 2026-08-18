import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.security import hash_access_token
from app.db.models import ConversionJob
from app.domain.jobs import JobStatus
from app.workers import tasks


def test_cleanup_expires_job_and_removes_files(
    app_context: dict[str, Any], monkeypatch: Any
) -> None:
    settings = app_context["settings"]
    source = Path(settings.storage_path, "source.pdf")
    result = Path(settings.storage_path, "result.docx")
    document_model = Path(settings.storage_path, "document-model.json")
    source_preview = Path(settings.storage_path, "source-preview.png")
    result_preview = Path(settings.storage_path, "result-preview.png")
    source.write_bytes(b"pdf")
    result.write_bytes(b"docx")
    document_model.write_text("{}")
    source_preview.write_bytes(b"png")
    result_preview.write_bytes(b"png")
    with app_context["session_factory"]() as session:
        job = ConversionJob(
            token_hash=hash_access_token("token", settings.token_pepper),
            mode="editable",
            source_key=source.name,
            result_key=result.name,
            document_model_key=document_model.name,
            source_preview_keys_json=json.dumps([source_preview.name]),
            result_preview_keys_json=json.dumps([result_preview.name]),
            original_filename="resume.pdf",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    monkeypatch.setattr(tasks, "SessionLocal", app_context["session_factory"])
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    assert tasks.cleanup_expired_jobs() == 1
    assert not source.exists()
    assert not result.exists()
    assert not document_model.exists()
    assert not source_preview.exists()
    assert not result_preview.exists()
    with app_context["session_factory"]() as session:
        assert session.get(ConversionJob, job_id).status is JobStatus.EXPIRED

    assert tasks.cleanup_expired_jobs() == 1
