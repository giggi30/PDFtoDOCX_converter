import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ConversionJob


class ConversionJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, job: ConversionJob) -> None:
        self.session.add(job)

    def get(self, job_id: uuid.UUID) -> ConversionJob | None:
        return self.session.get(ConversionJob, job_id)

    def delete(self, job: ConversionJob) -> None:
        self.session.delete(job)

    def expired_before(self, cutoff: datetime) -> list[ConversionJob]:
        statement = select(ConversionJob).where(ConversionJob.expires_at <= cutoff)
        return list(self.session.scalars(statement))

    def commit(self) -> None:
        self.session.commit()
