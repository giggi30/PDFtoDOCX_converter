import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

from docx import Document
from docx.oxml.ns import qn

from app.conversion.models import DocumentModel
from app.core.security import hash_access_token
from app.db.models import ConversionJob
from app.domain.jobs import JobStatus
from app.workers import tasks
from tests.fixtures.pdf_factory import CV_FIXTURES


def test_worker_creates_valid_editable_docx_from_document_model(
    app_context: dict[str, Any], monkeypatch: Any
) -> None:
    settings = app_context["settings"]
    source_key = "source.pdf"
    settings.storage_path.joinpath(source_key).write_bytes(CV_FIXTURES[0].pdf)
    with app_context["session_factory"]() as session:
        job = ConversionJob(
            token_hash=hash_access_token("token", settings.token_pepper),
            mode="editable",
            source_key=source_key,
            original_filename="resume.pdf",
            expires_at=datetime.now(UTC) + timedelta(minutes=60),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    monkeypatch.setattr(tasks, "SessionLocal", app_context["session_factory"])
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks,
        "render_docx",
        lambda content, **kwargs: tasks.render_pdf(CV_FIXTURES[0].pdf, dpi=settings.preview_dpi),
    )
    tasks.process_conversion(str(job_id))

    with app_context["session_factory"]() as session:
        completed = session.get(ConversionJob, uuid.UUID(str(job_id)))
        assert completed is not None
        assert completed.status is JobStatus.COMPLETED
        assert completed.result_key is not None
        assert completed.document_model_key is not None
        assert completed.quality_report_json is not None
        assert json.loads(completed.source_preview_keys_json)
        assert json.loads(completed.result_preview_keys_json)
        result_path = settings.storage_path / completed.result_key
        model_path = settings.storage_path / completed.document_model_key
        assert zipfile.is_zipfile(result_path)
        model = DocumentModel.model_validate_json(model_path.read_text())
        assert model.source_type == "native"
        assert "Candidate 01" in "\n".join(
            block.text for region in model.pages[0].regions for block in region.blocks
        )
        document = Document(io.BytesIO(result_path.read_bytes()))
        docx_text = "\n".join(
            node.text for node in document.element.body.iter(qn("w:t")) if node.text
        )
        assert "Candidate 01" in docx_text
        assert "Conversion placeholder" not in docx_text
        quality = json.loads(completed.quality_report_json)
        assert quality["overall_score"] >= 90
        assert quality["metrics"]["text_accuracy"] == 100
