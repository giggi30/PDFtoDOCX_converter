from dataclasses import dataclass
from typing import Literal

LayoutKind = Literal["single", "sidebar", "columns"]


@dataclass(frozen=True)
class CvFixture:
    name: str
    layout: LayoutKind
    pdf: bytes
    expected_text: tuple[str, ...]


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(
    text_items: list[tuple[float, float, str, float, bool]],
    rectangles: list[tuple[float, float, float, float, tuple[float, float, float]]] | None = None,
) -> bytes:
    """Build a small valid one-page PDF without adding a test-only PDF dependency."""
    commands: list[str] = []
    for x, y, text, size, bold in text_items:
        font = "F2" if bold else "F1"
        commands.append(
            f"BT /{font} {size:g} Tf 0 0 0 rg {x:g} {y:g} Td ({_pdf_escape(text)}) Tj ET"
        )
    for x, y, width, height, color in rectangles or []:
        red, green, blue = color
        commands.insert(0, f"{red:g} {green:g} {blue:g} rg {x:g} {y:g} {width:g} {height:g} re f")
    stream = "\n".join(commands).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [5 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents 6 0 R >>"
        ),
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
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


def _single(index: int) -> CvFixture:
    name = f"Candidate {index:02d}"
    items = [
        (48, 744, name, 20, True),
        (48, 714, "PROFESSIONAL PROFILE", 12, True),
        (48, 696, "Software professional focused on reliable products.", 10, False),
        (48, 660, "EXPERIENCE", 12, True),
        (48, 642, "Product Engineer - Example Studio", 10, True),
        (48, 626, "Built accessible web applications for international teams.", 10, False),
        (48, 590, "EDUCATION", 12, True),
        (48, 572, "Bachelor of Science - Example University", 10, False),
    ]
    return CvFixture(
        name=f"single-{index:02d}",
        layout="single",
        pdf=build_pdf(items),
        expected_text=(name, "PROFESSIONAL PROFILE", "EXPERIENCE", "EDUCATION"),
    )


def _sidebar(index: int) -> CvFixture:
    name = f"Candidate {index:02d}"
    items = [
        (34, 744, "CONTACT", 11, True),
        (34, 724, "candidate@example.test", 8, False),
        (34, 694, "SKILLS", 11, True),
        (34, 674, "Python", 9, False),
        (34, 658, "TypeScript", 9, False),
        (214, 744, name, 20, True),
        (214, 710, "EXPERIENCE", 12, True),
        (214, 690, "Product Engineer", 10, True),
        (214, 672, "Delivered maintainable products and clear documentation.", 9, False),
        (214, 628, "EDUCATION", 12, True),
        (214, 608, "Example University", 10, False),
    ]
    rectangles = [(0, 0, 180, 792, (0.88, 0.92, 0.96))]
    return CvFixture(
        name=f"sidebar-{index:02d}",
        layout="sidebar",
        pdf=build_pdf(items, rectangles),
        expected_text=(name, "CONTACT", "SKILLS", "EXPERIENCE"),
    )


def _columns(index: int) -> CvFixture:
    name = f"Candidate {index:02d}"
    items = [
        (48, 744, name, 20, True),
        (48, 706, "EXPERIENCE", 12, True),
        (48, 686, "Product Engineer", 10, True),
        (48, 668, "Built dependable services.", 9, False),
        (48, 632, "PROJECTS", 12, True),
        (48, 612, "Open source contributor", 9, False),
        (330, 706, "EDUCATION", 12, True),
        (330, 686, "Example University", 10, False),
        (330, 650, "SKILLS", 12, True),
        (330, 630, "Python and TypeScript", 9, False),
        (330, 594, "LANGUAGES", 12, True),
        (330, 574, "English and Italian", 9, False),
    ]
    return CvFixture(
        name=f"columns-{index:02d}",
        layout="columns",
        pdf=build_pdf(items),
        expected_text=(name, "EXPERIENCE", "PROJECTS", "EDUCATION", "SKILLS"),
    )


CV_FIXTURES = tuple(
    [_single(index) for index in range(1, 5)]
    + [_sidebar(index) for index in range(5, 8)]
    + [_columns(index) for index in range(8, 11)]
)
