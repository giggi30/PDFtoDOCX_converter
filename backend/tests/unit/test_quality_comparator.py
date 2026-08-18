import io

from PIL import Image, ImageDraw

from app.quality.comparator import compare_conversion
from app.quality.renderer import RenderedPage


def _page(*, rectangle: bool) -> RenderedPage:
    image = Image.new("RGB", (200, 300), "white")
    if rectangle:
        ImageDraw.Draw(image).rectangle((20, 20, 180, 100), fill="#123456")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return RenderedPage(page_number=1, png=stream.getvalue(), width_px=200, height_px=300)


def test_identical_render_and_text_receive_an_excellent_score() -> None:
    page = _page(rectangle=True)

    report = compare_conversion(
        [page],
        [page],
        source_text="An editable document",
        result_text="An editable document",
    )

    assert report.overall_score == 100
    assert report.rating == "excellent"
    assert report.metrics.visual_similarity == 100
    assert report.metrics.text_accuracy == 100
    assert report.differences == ["Non sono state rilevate differenze significative."]


def test_visual_text_and_page_differences_are_explained() -> None:
    report = compare_conversion(
        [_page(rectangle=True), _page(rectangle=True)],
        [_page(rectangle=False)],
        source_text="Complete original text",
        result_text="Incomplete text",
    )

    assert report.overall_score < 75
    assert report.rating in {"fair", "poor"}
    assert report.metrics.page_count_match == 50
    assert len(report.differences) >= 3
