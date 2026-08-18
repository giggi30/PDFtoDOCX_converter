"""Rendering and measurable conversion-quality assessment."""

from app.quality.comparator import compare_conversion, extract_docx_text
from app.quality.models import QualityReport
from app.quality.renderer import RenderedPage, render_docx, render_pdf

__all__ = [
    "QualityReport",
    "RenderedPage",
    "compare_conversion",
    "extract_docx_text",
    "render_docx",
    "render_pdf",
]
