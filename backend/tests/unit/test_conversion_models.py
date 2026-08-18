import pytest
from pydantic import ValidationError

from app.conversion.models import (
    BoundingBox,
    DocumentModel,
    PageModel,
    Region,
    TextBlock,
    TextStyle,
)


def test_document_model_is_json_round_trip_safe() -> None:
    model = DocumentModel(
        source_type="native",
        pages=[
            PageModel(
                page_number=1,
                width_pt=612,
                height_pt=792,
                regions=[
                    Region(
                        type="main",
                        bbox=BoundingBox(x0=40, y0=40, x1=572, y1=752),
                        blocks=[
                            TextBlock(
                                id="p1-b1",
                                bbox=BoundingBox(x0=40, y0=40, x1=200, y1=55),
                                text="Anonymous Candidate",
                                style=TextStyle(
                                    font_family="Helvetica",
                                    font_size=12,
                                    color="#000000",
                                ),
                                block_type="heading",
                            )
                        ],
                    )
                ],
            )
        ],
    )

    restored = DocumentModel.model_validate_json(model.model_dump_json())
    assert restored == model


def test_bounding_box_rejects_inverted_coordinates() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(x0=20, y0=10, x1=10, y1=30)
