import json
import uuid
from typing import Any

from app.db.models import ConversionJob
from app.domain.jobs import JobPhase, JobStatus
from tests.conftest import make_pdf


def upload(app_context: dict[str, Any]) -> dict[str, Any]:
    response = app_context["client"].post(
        "/api/v1/conversions",
        files={"file": ("resume.pdf", make_pdf(), "application/pdf")},
        data={"mode": "editable"},
    )
    assert response.status_code == 202
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_upload_persists_job_and_enqueues_it(app_context: dict[str, Any]) -> None:
    payload = upload(app_context)
    assert payload["status"] == "QUEUED"
    assert payload["access_token"]
    assert app_context["dispatcher"].job_ids == [uuid.UUID(payload["job_id"])]

    with app_context["session_factory"]() as session:
        job = session.get(ConversionJob, uuid.UUID(payload["job_id"]))
        assert job is not None
        assert job.token_hash != payload["access_token"]
        assert (app_context["settings"].storage_path / job.source_key).exists()


def test_poll_requires_the_temporary_token(app_context: dict[str, Any]) -> None:
    payload = upload(app_context)
    url = f"/api/v1/conversions/{payload['job_id']}"
    assert app_context["client"].get(url).status_code == 401
    assert app_context["client"].get(url, headers=auth("wrong")).status_code == 403
    response = app_context["client"].get(url, headers=auth(payload["access_token"]))
    assert response.status_code == 200
    assert response.json()["progress"] == 0


def test_download_and_delete_completed_job(app_context: dict[str, Any]) -> None:
    payload = upload(app_context)
    job_id = uuid.UUID(payload["job_id"])
    with app_context["session_factory"]() as session:
        job = session.get(ConversionJob, job_id)
        assert job is not None
        for phase in JobPhase:
            job.transition(JobStatus.PROCESSING, phase)
        result_key = "result.docx"
        app_context["settings"].storage_path.joinpath(result_key).write_bytes(b"PK dummy")
        source_preview_key = "source-preview.png"
        result_preview_key = "result-preview.png"
        app_context["settings"].storage_path.joinpath(source_preview_key).write_bytes(b"source")
        app_context["settings"].storage_path.joinpath(result_preview_key).write_bytes(b"result")
        job.result_key = result_key
        job.source_preview_keys_json = json.dumps([source_preview_key])
        job.result_preview_keys_json = json.dumps([result_preview_key])
        job.quality_report_json = json.dumps(
            {
                "overall_score": 88.5,
                "rating": "good",
                "metrics": {
                    "visual_similarity": 80,
                    "text_accuracy": 100,
                    "layout_similarity": 82.5,
                    "page_count_match": 100,
                },
                "differences": ["Layout difference"],
            }
        )
        job.transition(JobStatus.COMPLETED)
        session.commit()

    headers = auth(payload["access_token"])
    download = app_context["client"].get(f"/api/v1/conversions/{job_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == b"PK dummy"
    result = app_context["client"].get(f"/api/v1/conversions/{job_id}/result", headers=headers)
    assert result.status_code == 200
    assert result.json()["overall_score"] == 88.5
    assert result.json()["metrics"]["text_accuracy"] == 100
    source_preview = app_context["client"].get(
        result.json()["source_preview_urls"][0], headers=headers
    )
    assert source_preview.content == b"source"
    deleted = app_context["client"].delete(f"/api/v1/conversions/{job_id}", headers=headers)
    assert deleted.status_code == 200
    assert not app_context["settings"].storage_path.joinpath(source_preview_key).exists()
    assert not app_context["settings"].storage_path.joinpath(result_preview_key).exists()
    with app_context["session_factory"]() as session:
        assert session.get(ConversionJob, job_id) is None


def test_invalid_pdf_is_rejected_without_queueing(app_context: dict[str, Any]) -> None:
    response = app_context["client"].post(
        "/api/v1/conversions",
        files={"file": ("fake.pdf", b"not-pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert app_context["dispatcher"].job_ids == []
