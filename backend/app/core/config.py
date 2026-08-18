from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://pdf_converter:pdf_converter@postgres/pdf_converter"
    redis_url: str = "redis://redis:6379/0"
    storage_path: Path = Path("/tmp/pdf-to-docx")
    job_ttl_minutes: int = Field(default=60, ge=1, le=60)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=5, ge=1)
    token_pepper: str = Field(default="development-only-change-me", min_length=16)
    rq_queue_name: str = "conversions"
    preview_dpi: int = Field(default=96, ge=72, le=200)
    libreoffice_binary: str = "soffice"
    libreoffice_timeout_seconds: int = Field(default=30, ge=5, le=120)


@lru_cache
def get_settings() -> Settings:
    return Settings()
