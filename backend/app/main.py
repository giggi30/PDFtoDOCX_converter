from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.conversions import router as conversions_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="PDF to DOCX Platform API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(conversions_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
