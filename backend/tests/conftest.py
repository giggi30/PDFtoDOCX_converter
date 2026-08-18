import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.queue import get_dispatcher


class RecordingDispatcher:
    def __init__(self) -> None:
        self.job_ids: list[uuid.UUID] = []

    def enqueue(self, job_id: uuid.UUID) -> None:
        self.job_ids.append(job_id)


def make_pdf(page_count: int = 1) -> bytes:
    objects: list[bytes] = []
    page_ids = [3 + index * 2 for index in range(page_count)]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
    for index, page_id in enumerate(page_ids):
        content_id = page_id + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        stream = f"BT /F1 12 Tf 72 720 Td (Synthetic page {index + 1}) Tj ET".encode()
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    )
    output.extend(trailer.encode())
    return bytes(output)


@pytest.fixture
def app_context(tmp_path: Path) -> Generator[dict[str, Any], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        storage_path=tmp_path,
        token_pepper="test-pepper-is-long-enough",
    )
    dispatcher = RecordingDispatcher()

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_dispatcher] = lambda: dispatcher
    with TestClient(app) as client:
        yield {
            "client": client,
            "dispatcher": dispatcher,
            "session_factory": testing_session,
            "settings": settings,
        }
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
