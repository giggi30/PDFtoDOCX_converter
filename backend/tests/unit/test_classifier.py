from app.conversion.classifier import PageSignals, classify_pdf


def test_classifies_native_pdf() -> None:
    assert classify_pdf([PageSignals(text_character_count=300)]) == "native"


def test_classifies_scanned_pdf() -> None:
    assert (
        classify_pdf([PageSignals(text_character_count=0, largest_image_coverage=0.96)])
        == "scanned"
    )


def test_classifies_hybrid_pdf_from_mixed_pages() -> None:
    assert (
        classify_pdf(
            [
                PageSignals(text_character_count=250),
                PageSignals(text_character_count=0, largest_image_coverage=0.95),
            ]
        )
        == "hybrid"
    )


def test_classifies_ocr_text_over_a_page_image_as_hybrid() -> None:
    assert (
        classify_pdf([PageSignals(text_character_count=250, largest_image_coverage=0.95)])
        == "hybrid"
    )
