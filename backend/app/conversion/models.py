from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

SourceType = Literal["native", "scanned", "hybrid"]
BlockType = Literal["heading", "paragraph", "list_item"]
RegionType = Literal["header", "footer", "hero", "card", "sidebar", "main", "column"]


class BoundingBox(BaseModel):
    """Coordinates in PDF points, using a top-left origin."""

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def validate_extents(self) -> Self:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("Bounding box coordinates must not be inverted")
        return self

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @classmethod
    def enclosing(cls, boxes: list["BoundingBox"]) -> "BoundingBox":
        if not boxes:
            raise ValueError("At least one bounding box is required")
        return cls(
            x0=min(box.x0 for box in boxes),
            y0=min(box.y0 for box in boxes),
            x1=max(box.x1 for box in boxes),
            y1=max(box.y1 for box in boxes),
        )


class TextStyle(BaseModel):
    font_family: str | None
    font_size: float = Field(gt=0)
    color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    bold: bool = False
    italic: bool = False
    underline: bool = False


class TextBlock(BaseModel):
    id: str
    bbox: BoundingBox
    text: str
    style: TextStyle
    block_type: BlockType


class ImageElement(BaseModel):
    id: str
    bbox: BoundingBox
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    role: Literal["photo", "icon", "background", "image"] = "image"
    mime_type: Literal["image/png"] | None = None
    content_base64: str | None = None


class Decoration(BaseModel):
    id: str
    bbox: BoundingBox
    kind: Literal["rectangle", "line", "curve"]
    fill_color: str | None = Field(default=None, pattern=r"^#[0-9A-F]{6}$")
    stroke_color: str | None = Field(default=None, pattern=r"^#[0-9A-F]{6}$")
    stroke_width: float | None = Field(default=None, ge=0)


class Region(BaseModel):
    type: RegionType
    bbox: BoundingBox
    blocks: list[TextBlock]


class PageModel(BaseModel):
    page_number: int = Field(ge=1)
    width_pt: float = Field(gt=0)
    height_pt: float = Field(gt=0)
    regions: list[Region]
    images: list[ImageElement] = Field(default_factory=list)
    decorations: list[Decoration] = Field(default_factory=list)


class DocumentModel(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source_type: SourceType
    pages: list[PageModel]
    warnings: list[str] = Field(default_factory=list)


class ExtractedPage(BaseModel):
    """Library-neutral page elements before region detection."""

    page_number: int = Field(ge=1)
    width_pt: float = Field(gt=0)
    height_pt: float = Field(gt=0)
    blocks: list[TextBlock]
    images: list[ImageElement] = Field(default_factory=list)
    decorations: list[Decoration] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    source_type: SourceType
    pages: list[ExtractedPage]
    warnings: list[str] = Field(default_factory=list)
