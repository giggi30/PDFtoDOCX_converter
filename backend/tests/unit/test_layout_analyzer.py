from app.conversion.extractor import extract_pdf
from app.conversion.layout_analyzer import analyze_layout
from tests.fixtures.pdf_factory import CV_FIXTURES, build_pdf


def test_detects_single_column_layout() -> None:
    fixture = next(item for item in CV_FIXTURES if item.layout == "single")
    model = analyze_layout(extract_pdf(fixture.pdf))

    assert [region.type for region in model.pages[0].regions] == ["main"]


def test_detects_sidebar_and_main_regions() -> None:
    fixture = next(item for item in CV_FIXTURES if item.layout == "sidebar")
    model = analyze_layout(extract_pdf(fixture.pdf))

    assert [region.type for region in model.pages[0].regions] == ["sidebar", "main"]
    assert model.pages[0].regions[0].bbox.x1 < model.pages[0].regions[1].bbox.x0


def test_detects_two_columns_in_left_to_right_reading_order() -> None:
    fixture = next(item for item in CV_FIXTURES if item.layout == "columns")
    model = analyze_layout(extract_pdf(fixture.pdf))

    assert [region.type for region in model.pages[0].regions] == ["header", "column", "column"]
    assert "EXPERIENCE" in model.pages[0].regions[1].blocks[0].text
    assert "EDUCATION" in model.pages[0].regions[2].blocks[0].text


def test_detects_hero_and_bottom_card_as_local_zones() -> None:
    pdf = build_pdf(
        [
            (72, 730, "ANONYMOUS CANDIDATE", 22, True),
            (72, 690, "Software Professional", 16, False),
            (48, 600, "PROFILE", 12, True),
            (48, 575, "Editable professional summary.", 10, False),
            (340, 105, "candidate@example.test", 10, False),
            (340, 80, "Example City", 10, False),
        ],
        rectangles=[
            (0, 652, 612, 140, (0.03, 0.18, 0.39)),
            (310, 20, 290, 130, (0.87, 0.93, 1.0)),
        ],
    )

    model = analyze_layout(extract_pdf(pdf))

    assert [region.type for region in model.pages[0].regions] == ["hero", "main", "card"]
    assert len(model.pages[0].regions[0].blocks) == 2
    assert "PROFILE" in model.pages[0].regions[1].blocks[0].text
    assert len(model.pages[0].regions[2].blocks) == 2
