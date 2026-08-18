from app.quality.renderer import render_pdf
from tests.fixtures.pdf_factory import CV_FIXTURES


def test_renders_pdf_pages_as_png_previews() -> None:
    pages = render_pdf(CV_FIXTURES[0].pdf, dpi=72)

    assert len(pages) == 1
    assert pages[0].png.startswith(b"\x89PNG")
    assert pages[0].width_px == 612
    assert pages[0].height_px == 792
