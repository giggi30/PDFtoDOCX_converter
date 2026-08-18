from pathlib import Path

import pytest

from app.conversion.models import DocumentModel
from app.conversion.pipeline import pdf_to_document_model
from tests.fixtures.pdf_factory import CV_FIXTURES, CvFixture

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("fixture", CV_FIXTURES, ids=lambda fixture: fixture.name)
def test_ten_anonymous_cv_fixtures_produce_coherent_models(fixture: CvFixture) -> None:
    model = pdf_to_document_model(fixture.pdf)

    assert model.source_type == "native"
    assert len(model.pages) == 1
    assert model.pages[0].width_pt == 612
    assert model.pages[0].height_pt == 792
    extracted_text = "\n".join(
        block.text for region in model.pages[0].regions for block in region.blocks
    )
    assert all(expected in extracted_text for expected in fixture.expected_text)
    if fixture.layout == "single":
        assert [region.type for region in model.pages[0].regions] == ["main"]
    elif fixture.layout == "sidebar":
        assert {region.type for region in model.pages[0].regions} == {"sidebar", "main"}
    else:
        assert [region.type for region in model.pages[0].regions].count("column") == 2
    assert DocumentModel.model_validate_json(model.model_dump_json()) == model


def test_canva_fixture_detects_hero_and_two_local_columns() -> None:
    source = _PROJECT_ROOT / "test-documents/fixtures/Curriculum Vitae.pdf"

    model = pdf_to_document_model(source.read_bytes())
    page = model.pages[0]

    assert [region.type for region in page.regions] == ["hero", "column", "column"]
    assert [block.text for block in page.regions[0].blocks] == [
        "Carlo Giddi",
        "Personal Trainer",
    ]
    assert sum(
        block.block_type == "list_item"
        for region in page.regions[1:]
        for block in region.blocks
    ) == 8
    assert any(
        decoration.bbox.width <= 2 and decoration.bbox.height > page.height_pt * 0.5
        for decoration in page.decorations
    )
