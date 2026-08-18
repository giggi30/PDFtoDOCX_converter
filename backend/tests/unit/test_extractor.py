import base64
import io

from PIL import Image

from app.conversion.extractor import extract_pdf
from tests.fixtures.pdf_factory import build_pdf


def _pdf_with_embedded_image() -> bytes:
    pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0])
    commands = b"q 72 0 0 72 48 650 cm /Im1 Do Q"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        f"<< /Length {len(commands)} >>\nstream\n".encode() + commands + b"\nendstream",
        (
            b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
            b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 12 >>\nstream\n"
            + pixels
            + b"\nendstream"
        ),
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)


def test_extracts_text_coordinates_and_style() -> None:
    pdf = build_pdf(
        [
            (48, 744, "ANONYMOUS CANDIDATE", 18, True),
            (48, 716, "Profile text", 10, False),
        ]
    )

    extracted = extract_pdf(pdf)

    assert extracted.source_type == "native"
    assert len(extracted.pages) == 1
    blocks = extracted.pages[0].blocks
    assert [block.text for block in blocks] == ["ANONYMOUS CANDIDATE", "Profile text"]
    assert blocks[0].style.bold is True
    assert blocks[0].style.font_size == 18
    assert blocks[0].bbox.x0 == 48
    assert blocks[0].bbox.y0 < blocks[1].bbox.y0


def test_groups_adjacent_lines_into_a_paragraph_block() -> None:
    pdf = build_pdf(
        [
            (48, 700, "First wrapped line", 10, False),
            (48, 688, "second wrapped line", 10, False),
        ]
    )

    blocks = extract_pdf(pdf).pages[0].blocks

    assert len(blocks) == 1
    assert blocks[0].text == "First wrapped line\nsecond wrapped line"
    assert blocks[0].block_type == "paragraph"


def test_extracts_sidebar_rectangle_as_decoration() -> None:
    pdf = build_pdf(
        [(220, 720, "EXPERIENCE", 12, True)],
        [(0, 0, 180, 792, (0.8, 0.9, 1.0))],
    )

    decorations = extract_pdf(pdf).pages[0].decorations

    assert len(decorations) == 1
    assert decorations[0].kind == "rectangle"
    assert decorations[0].fill_color == "#CCE6FF"


def test_extracts_embeddable_png_content_for_pdf_images() -> None:
    image = extract_pdf(_pdf_with_embedded_image()).pages[0].images[0]

    assert image.mime_type == "image/png"
    assert image.content_base64 is not None
    rendered = Image.open(io.BytesIO(base64.b64decode(image.content_base64)))
    assert rendered.format == "PNG"
    assert rendered.width > 1
    assert rendered.height > 1


def test_ignores_vector_icons_outside_the_visible_page() -> None:
    pdf = build_pdf(
        [(48, 744, "Candidate", 18, True)],
        [(20, 815, 20, 20, (0.2, 0.3, 0.4))],
    )

    extracted = extract_pdf(pdf)

    assert extracted.pages[0].images == []
