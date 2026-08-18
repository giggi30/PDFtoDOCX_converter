import pytest

from app.services.pdf_validation import InvalidPdfError, validate_pdf
from tests.conftest import make_pdf


def test_accepts_native_pdf_within_limits() -> None:
    content = make_pdf()
    validate_pdf(content, "application/pdf", 10_000, 5)


@pytest.mark.parametrize(
    ("content", "mime"),
    [(b"not a pdf", "application/pdf"), (b"%PDF-invalid", "text/plain")],
)
def test_rejects_invalid_upload(content: bytes, mime: str) -> None:
    with pytest.raises(InvalidPdfError):
        validate_pdf(content, mime, 10_000, 5)


def test_rejects_too_many_pages() -> None:
    with pytest.raises(InvalidPdfError, match="5 page"):
        validate_pdf(make_pdf(6), "application/pdf", 100_000, 5)
