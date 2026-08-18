import uuid
from typing import Any

from app.db.models import ConversionJob
from app.workers import tasks
from tests.fixtures.pdf_factory import CV_FIXTURES


def test_upload_worker_quality_previews_and_download_flow(
    app_context: dict[str, Any], monkeypatch: Any
) -> None:
    fixture = CV_FIXTURES[0]
    response = app_context["client"].post(
        "/api/v1/conversions",
        files={"file": ("anonymous-cv.pdf", fixture.pdf, "application/pdf")},
        data={"mode": "editable"},
    )
    assert response.status_code == 202
    created = response.json()
    job_id = uuid.UUID(created["job_id"])
    headers = {"Authorization": f"Bearer {created['access_token']}"}

    settings = app_context["settings"]
    monkeypatch.setattr(tasks, "SessionLocal", app_context["session_factory"])
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks,
        "render_docx",
        lambda content, **kwargs: tasks.render_pdf(fixture.pdf, dpi=settings.preview_dpi),
    )
    tasks.process_conversion(str(job_id))

    status_response = app_context["client"].get(f"/api/v1/conversions/{job_id}", headers=headers)
    assert status_response.json()["status"] == "COMPLETED"
    assert status_response.json()["progress"] == 100

    result_response = app_context["client"].get(
        f"/api/v1/conversions/{job_id}/result", headers=headers
    )
    result = result_response.json()
    assert result_response.status_code == 200
    assert result["overall_score"] >= 90
    assert result["rating"] == "excellent"
    assert len(result["source_preview_urls"]) == 1
    assert len(result["result_preview_urls"]) == 1

    for preview_url in result["source_preview_urls"] + result["result_preview_urls"]:
        preview = app_context["client"].get(preview_url, headers=headers)
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.content.startswith(b"\x89PNG")

    download = app_context["client"].get(f"/api/v1/conversions/{job_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content.startswith(b"PK")

    with app_context["session_factory"]() as session:
        persisted = session.get(ConversionJob, job_id)
        assert persisted is not None
        assert persisted.quality_report_json is not None
