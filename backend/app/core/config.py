import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, model_validator
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

    @model_validator(mode="after")
    def validate_runtime_urls(self) -> "Settings":
        # Docker service names work locally in Compose, but never on Vercel.
        if os.getenv("VERCEL") == "1":
            db_host = urlparse(self.database_url).hostname
            redis_host = urlparse(self.redis_url).hostname
            if db_host == "postgres":
                raise ValueError(
                    "APP_DATABASE_URL points to 'postgres', which is only valid in Docker Compose. "
                    "Set APP_DATABASE_URL to a managed PostgreSQL host for Vercel."
                )
            if redis_host == "redis":
                raise ValueError(
                    "APP_REDIS_URL points to 'redis', which is only valid in Docker Compose. "
                    "Set APP_REDIS_URL to a managed Redis host for Vercel."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
