import io

import pdfplumber


class InvalidPdfError(ValueError):
    pass


def validate_pdf(content: bytes, content_type: str | None, max_bytes: int, max_pages: int) -> None:
    if not content:
        raise InvalidPdfError("The uploaded file is empty")
    if len(content) > max_bytes:
        raise InvalidPdfError("The uploaded file exceeds the 10 MB limit")
    if content_type not in {"application/pdf", "application/octet-stream"}:
        raise InvalidPdfError("The uploaded file must have PDF MIME type")
    if not content.startswith(b"%PDF-"):
        raise InvalidPdfError("The uploaded file does not have valid PDF magic bytes")
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if len(pdf.pages) > max_pages:
                raise InvalidPdfError("The PDF exceeds the 5 page limit")
            if len(pdf.pages) == 0:
                raise InvalidPdfError("The PDF has no pages")
    except InvalidPdfError:
        raise
    except Exception as exc:
        raise InvalidPdfError("The PDF is malformed or encrypted") from exc
