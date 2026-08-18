from typing import Literal

from pydantic import BaseModel, Field


class QualityMetrics(BaseModel):
    visual_similarity: float = Field(ge=0, le=100)
    text_accuracy: float = Field(ge=0, le=100)
    layout_similarity: float = Field(ge=0, le=100)
    page_count_match: float = Field(ge=0, le=100)


class QualityReport(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    rating: Literal["excellent", "good", "fair", "poor"]
    metrics: QualityMetrics
    differences: list[str] = Field(default_factory=list)
