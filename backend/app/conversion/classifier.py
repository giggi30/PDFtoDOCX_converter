from collections.abc import Sequence
from dataclasses import dataclass

from app.conversion.models import SourceType


@dataclass(frozen=True)
class PageSignals:
    text_character_count: int
    image_count: int = 0
    largest_image_coverage: float = 0.0


def classify_pdf(pages: Sequence[PageSignals], minimum_native_characters: int = 20) -> SourceType:
    """Classify from neutral page signals rather than pdfplumber objects."""
    if not pages:
        return "scanned"

    text_pages = [page for page in pages if page.text_character_count >= minimum_native_characters]
    scanned_pages = [
        page
        for page in pages
        if page.text_character_count < minimum_native_characters
        and page.largest_image_coverage >= 0.5
    ]
    text_over_page_image = any(
        page.text_character_count >= minimum_native_characters
        and page.largest_image_coverage >= 0.5
        for page in pages
    )
    if text_over_page_image or (text_pages and scanned_pages):
        return "hybrid"
    if text_pages:
        return "native"
    return "scanned"
