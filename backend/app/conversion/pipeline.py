from app.conversion.extractor import extract_pdf
from app.conversion.layout_analyzer import analyze_layout
from app.conversion.models import DocumentModel


def pdf_to_document_model(content: bytes) -> DocumentModel:
    return analyze_layout(extract_pdf(content))
