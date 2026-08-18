import base64
import io
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pdfplumber
from PIL import ImageDraw

from app.conversion.classifier import PageSignals, classify_pdf
from app.conversion.models import (
    BoundingBox,
    Decoration,
    ExtractedDocument,
    ExtractedPage,
    ImageElement,
    TextBlock,
    TextStyle,
)

_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")


@dataclass(frozen=True)
class _Glyph:
    text: str
    bbox: BoundingBox
    style: TextStyle


@dataclass(frozen=True)
class _TextLine:
    text: str
    bbox: BoundingBox
    style: TextStyle


def _normalise_font_name(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return _SUBSET_PREFIX.sub("", value)


def _colour(value: object) -> str:
    if value is None:
        return "#000000"
    if isinstance(value, (int, float)):
        components = [float(value)]
    elif isinstance(value, (list, tuple)):
        components = [float(item) for item in value if isinstance(item, (int, float))]
    else:
        return "#000000"
    if len(components) == 1:
        red = green = blue = components[0]
    elif len(components) == 3:
        red, green, blue = components
    elif len(components) == 4:
        cyan, magenta, yellow, black = components
        red = (1 - cyan) * (1 - black)
        green = (1 - magenta) * (1 - black)
        blue = (1 - yellow) * (1 - black)
    else:
        return "#000000"
    rgb = tuple(round(max(0.0, min(1.0, channel)) * 255) for channel in (red, green, blue))
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _style(character: dict[str, Any]) -> TextStyle:
    font_name = _normalise_font_name(character.get("fontname"))
    searchable_name = (font_name or "").lower()
    size = float(character.get("size") or 1.0)
    return TextStyle(
        font_family=font_name,
        font_size=round(size, 3),
        color=_colour(character.get("non_stroking_color")),
        bold=any(token in searchable_name for token in ("bold", "black", "semibold", "demi")),
        italic=any(token in searchable_name for token in ("italic", "oblique")),
    )


def _bbox(item: dict[str, Any], page_height: float) -> BoundingBox:
    x0 = float(item.get("x0", 0.0))
    x1 = float(item.get("x1", x0))
    if "top" in item and "bottom" in item:
        top = float(item["top"])
        bottom = float(item["bottom"])
    else:
        y0 = float(item.get("y0", 0.0))
        y1 = float(item.get("y1", y0))
        top = page_height - max(y0, y1)
        bottom = page_height - min(y0, y1)
    return BoundingBox(x0=min(x0, x1), y0=min(top, bottom), x1=max(x0, x1), y1=max(top, bottom))


def _glyphs(characters: list[dict[str, Any]], page_height: float) -> list[_Glyph]:
    return [
        _Glyph(text=str(item.get("text", "")), bbox=_bbox(item, page_height), style=_style(item))
        for item in characters
        if str(item.get("text", ""))
    ]


def _dominant_style(glyphs: list[_Glyph]) -> TextStyle:
    counts = Counter(
        (
            glyph.style.font_family,
            glyph.style.font_size,
            glyph.style.color,
            glyph.style.bold,
            glyph.style.italic,
            glyph.style.underline,
        )
        for glyph in glyphs
        if not glyph.text.isspace()
    )
    if not counts:
        return glyphs[0].style
    values = counts.most_common(1)[0][0]
    return TextStyle(
        font_family=values[0],
        font_size=values[1],
        color=values[2],
        bold=values[3],
        italic=values[4],
        underline=values[5],
    )


def _group_glyphs_into_lines(glyphs: list[_Glyph]) -> list[_TextLine]:
    grouped: list[list[_Glyph]] = []
    for glyph in sorted(glyphs, key=lambda item: (item.bbox.y0, item.bbox.x0)):
        matching: list[_Glyph] | None = None
        for candidate in reversed(grouped[-4:]):
            reference_top = sum(item.bbox.y0 for item in candidate) / len(candidate)
            # Increase tolerance to handle jitter in poorly generated PDFs
            tolerance = max(2.5, glyph.style.font_size * 0.4)
            if abs(glyph.bbox.y0 - reference_top) <= tolerance:
                matching = candidate
                break
        if matching is None:
            grouped.append([glyph])
        else:
            matching.append(glyph)

    lines: list[_TextLine] = []
    for line_glyphs in grouped:
        ordered = sorted(line_glyphs, key=lambda item: item.bbox.x0)
        segments: list[list[_Glyph]] = [[]]
        for glyph in ordered:
            previous = segments[-1][-1] if segments[-1] else None
            if previous is not None:
                gap = glyph.bbox.x0 - previous.bbox.x1
                if gap > max(20.0, min(previous.style.font_size, glyph.style.font_size) * 3):
                    segments.append([])
            segments[-1].append(glyph)

        for segment in segments:
            lines.append(_line_from_glyphs(segment))
    return sorted(lines, key=lambda item: (item.bbox.y0, item.bbox.x0))


def _line_from_glyphs(ordered: list[_Glyph]) -> _TextLine:
    text_parts: list[str] = []
    previous: _Glyph | None = None
    for glyph in ordered:
        if previous is not None and not previous.text.isspace() and not glyph.text.isspace():
            gap = glyph.bbox.x0 - previous.bbox.x1
            if gap > max(1.5, min(previous.style.font_size, glyph.style.font_size) * 0.2):
                text_parts.append(" ")
        text_parts.append(glyph.text)
        previous = glyph
    text = "".join(text_parts).strip()
    return _TextLine(
        text=text,
        bbox=BoundingBox.enclosing([item.bbox for item in ordered]),
        style=_dominant_style(ordered),
    )


def _same_style(first: TextStyle, second: TextStyle) -> bool:
    return (
        first.font_family == second.font_family
        and abs(first.font_size - second.font_size) <= 0.5
        and first.color == second.color
        and first.bold == second.bold
        and first.italic == second.italic
    )


def _block_type(text: str, style: TextStyle, median_size: float) -> str:
    stripped = text.lstrip()
    if stripped.startswith(("•", "‣", "▪", "- ", "– ", "— ")):
        return "list_item"
    if len(text.replace("\n", " ")) <= 120 and (
        style.font_size >= median_size * 1.18 or style.bold
    ):
        return "heading"
    return "paragraph"


def _group_lines_into_blocks(lines: list[_TextLine], page_number: int) -> list[TextBlock]:
    if not lines:
        return []
    sizes = sorted(line.style.font_size for line in lines)
    median_size = sizes[len(sizes) // 2]
    groups: list[list[_TextLine]] = []
    for line in lines:
        if groups:
            previous = groups[-1][-1]
            vertical_gap = line.bbox.y0 - previous.bbox.y1
            aligned = abs(line.bbox.x0 - previous.bbox.x0) <= 6.0
            # Increase merge tolerance to avoid overlapping blocks for headings
            # and to handle lines that might be slightly misaligned in Canva
            merge = (
                aligned
                and -6.0 <= vertical_gap <= max(8.0, line.style.font_size * 1.0)
                and _same_style(previous.style, line.style)
                and not line.text.lstrip().startswith(("•", "- ", "– ", "— "))
            )
            if merge:
                groups[-1].append(line)
                continue
        groups.append([line])

    blocks: list[TextBlock] = []
    for index, group in enumerate(groups, start=1):
        text = "\n".join(line.text for line in group)
        style = group[0].style
        blocks.append(
            TextBlock(
                id=f"page-{page_number}-block-{index}",
                bbox=BoundingBox.enclosing([line.bbox for line in group]),
                text=text,
                style=style,
                block_type=_block_type(text, style, median_size),
            )
        )
    return blocks


def _render_image_crop(page: Any, box: BoundingBox) -> str | None:
    try:
        cropped = page.crop((box.x0, box.y0, box.x1, box.y1), strict=False)
        rendered = cropped.to_image(resolution=144, antialias=True).original
        stream = io.BytesIO()
        rendered.save(stream, format="PNG")
        return base64.b64encode(stream.getvalue()).decode("ascii")
    except Exception:
        return None


def _render_transparent_vector_crop(
    page: Any,
    box: BoundingBox,
    *,
    background_color: str,
    text_blocks: Sequence[TextBlock] = (),
    extra_bboxes: Sequence[BoundingBox] = (),
) -> str | None:
    """Rasterize a vector-only fallback while keeping text editable above it."""
    try:
        cropped = page.crop((box.x0, box.y0, box.x1, box.y1), strict=False)
        source = cropped.to_image(resolution=216, antialias=True).original.convert("RGBA")
        base = tuple(int(background_color[index : index + 2], 16) for index in (1, 3, 5))
        pixels: list[tuple[int, int, int, int]] = []
        for red, green, blue, _ in source.getdata():
            close_to_background = max(
                abs(red - base[0]), abs(green - base[1]), abs(blue - base[2])
            ) <= 22
            neutral_light = min(red, green, blue) >= 165 and max(red, green, blue) - min(
                red, green, blue
            ) <= 45
            pixels.append((red, green, blue, 0 if close_to_background or neutral_light else 255))
        source.putdata(pixels)
        # Mask out all text found in the source to avoid "shadow" text in the image.
        mask = ImageDraw.Draw(source)
        scale_x = source.width / max(box.width, 0.01)
        scale_y = source.height / max(box.height, 0.01)
        # Increase padding to catch shadows (which are usually 1-3pt offset)
        padding_px = max(8, round(max(scale_x, scale_y) * 2.5))
        
        all_masks = [b.bbox for b in text_blocks] + list(extra_bboxes)
        for mask_box in all_masks:
            overlap_x0 = max(box.x0, mask_box.x0)
            overlap_y0 = max(box.y0, mask_box.y0)
            overlap_x1 = min(box.x1, mask_box.x1)
            overlap_y1 = min(box.y1, mask_box.y1)
            if overlap_x1 <= overlap_x0 or overlap_y1 <= overlap_y0:
                continue
            mask.rectangle(
                (
                    round((overlap_x0 - box.x0) * scale_x) - padding_px,
                    round((overlap_y0 - box.y0) * scale_y) - padding_px,
                    round((overlap_x1 - box.x0) * scale_x) + padding_px,
                    round((overlap_y1 - box.y0) * scale_y) + padding_px,
                ),
                fill=(0, 0, 0, 0),
            )
        stream = io.BytesIO()
        source.save(stream, format="PNG")
        return base64.b64encode(stream.getvalue()).decode("ascii")
    except Exception:
        return None


def _vector_backgrounds(
    page: Any,
    page_number: int,
    page_height: float,
    images: list[ImageElement],
    text_blocks: list[TextBlock],
    glyphs: Sequence[_Glyph] = (),
) -> list[ImageElement]:
    """Preserve complex vector artwork as page-anchored transparent overlays."""
    overlays: list[ImageElement] = []
    index = 1
    glyph_bboxes = [g.bbox for g in glyphs]
    for rect in page.rects:
        box = _bbox(rect, page_height)
        color = _colour(rect.get("non_stroking_color")) if rect.get("fill") else None
        is_top_banner = (
            color is not None
            and color not in {"#000000", "#FFFFFF"}
            and box.width >= float(page.width) * 0.75
            and box.y0 <= float(page.height) * 0.05
        )
        if not is_top_banner:
            continue
        curve_count = sum(
            1
            for curve in page.curves
            if _bbox(curve, page_height).x1 >= box.x0
            and _bbox(curve, page_height).x0 <= box.x1
            and _bbox(curve, page_height).y1 >= box.y0
            and _bbox(curve, page_height).y0 <= box.y1
        )
        if curve_count < 6:
            continue
        photo_left = min(
            (
                image.bbox.x0
                for image in images
                if image.role == "photo"
                and image.bbox.y0 < box.y1
                and image.bbox.y1 > box.y0
            ),
            default=box.x1,
        )
        overlay_box = BoundingBox(
            x0=max(0.0, box.x0),
            y0=max(0.0, box.y0),
            x1=min(float(page.width), box.x1, photo_left),
            y1=min(float(page.height), box.y1),
        )
        if overlay_box.width <= 0 or overlay_box.height <= 0:
            continue
        if color is None:
            continue
        content_base64 = _render_transparent_vector_crop(
            page,
            overlay_box,
            background_color=color,
            text_blocks=text_blocks,
            extra_bboxes=glyph_bboxes + [img.bbox for img in images if img.role != "background"],
        )
        if content_base64:
            overlays.append(
                ImageElement(
                    id=f"page-{page_number}-vector-background-{index}",
                    bbox=overlay_box,
                    role="background",
                    mime_type="image/png",
                    content_base64=content_base64,
                )
            )
            index += 1
    for line in page.lines:
        box = _bbox(line, page_height)
        if not (30 <= box.width <= 160 and box.height <= 2):
            continue
        overlay_box = BoundingBox(
            x0=max(0.0, box.x0 - 1),
            y0=max(0.0, box.y0 - 5),
            x1=min(float(page.width), box.x1 + 1),
            y1=min(float(page.height), box.y1 + 5),
        )
        content_base64 = _render_transparent_vector_crop(
            page,
            overlay_box,
            background_color="#FFFFFF",
            text_blocks=text_blocks,
            extra_bboxes=glyph_bboxes + [img.bbox for img in images if img.role != "background"],
        )
        if content_base64:
            overlays.append(
                ImageElement(
                    id=f"page-{page_number}-vector-background-{index}",
                    bbox=overlay_box,
                    role="background",
                    mime_type="image/png",
                    content_base64=content_base64,
                )
            )
            index += 1
    return overlays


def _vector_icons(
    page: Any, page_number: int, page_height: float, existing_images: list[ImageElement]
) -> list[ImageElement]:
    shapes: list[BoundingBox] = []
    for item in page.curves + page.rects:
        box = _bbox(item, page_height)
        is_icon_size = (
            4 <= box.width <= 40
            and 4 <= box.height <= 40
            and 0.5 <= box.width / max(box.height, 0.01) <= 2.0
        )
        if is_icon_size:
            if box.width < 3.5 and box.height < 3.5:
                continue
            if any(
                max(img.bbox.x0, box.x0) <= min(img.bbox.x1, box.x1)
                and max(img.bbox.y0, box.y0) <= min(img.bbox.y1, box.y1)
                for img in existing_images
            ):
                continue
            shapes.append(box)

    clusters: list[BoundingBox] = []
    for s in shapes:
        merged = False
        for cl in clusters:
            if (abs(s.x0 - cl.x0) <= 6 and abs(s.y0 - cl.y0) <= 6) or (
                max(cl.x0, s.x0) <= min(cl.x1, s.x1) and max(cl.y0, s.y0) <= min(cl.y1, s.y1)
            ):
                merged_box = BoundingBox(
                    x0=min(cl.x0, s.x0),
                    y0=min(cl.y0, s.y0),
                    x1=max(cl.x1, s.x1),
                    y1=max(cl.y1, s.y1),
                )
                clusters[clusters.index(cl)] = merged_box
                merged = True
                break
        if not merged:
            clusters.append(s)

    icons: list[ImageElement] = []
    start_index = len(existing_images) + 1
    for index, box in enumerate(clusters, start=start_index):
        visible_x0 = max(0.0, box.x0 - 0.5)
        visible_y0 = max(0.0, box.y0 - 0.5)
        visible_x1 = min(float(page.width), box.x1 + 0.5)
        visible_y1 = min(float(page.height), box.y1 + 0.5)
        if visible_x1 <= visible_x0 or visible_y1 <= visible_y0:
            continue
        padded_box = BoundingBox(
            x0=visible_x0,
            y0=visible_y0,
            x1=visible_x1,
            y1=visible_y1,
        )
        content_base64 = _render_image_crop(page, padded_box)
        if content_base64:
            icons.append(
                ImageElement(
                    id=f"page-{page_number}-icon-{index}",
                    bbox=padded_box,
                    role="icon",
                    mime_type="image/png",
                    content_base64=content_base64,
                )
            )
    return icons


def _images(page: Any, page_number: int, page_height: float) -> list[ImageElement]:
    images: list[ImageElement] = []
    for index, item in enumerate(page.images, start=1):
        box = _bbox(item, page_height)
        source_size = item.get("srcsize")
        width_px: int | None = None
        height_px: int | None = None
        if isinstance(source_size, (list, tuple)) and len(source_size) == 2:
            width_px = max(1, int(source_size[0]))
            height_px = max(1, int(source_size[1]))
        role = "photo" if 0.7 <= box.width / max(box.height, 0.01) <= 1.4 else "image"
        content_base64 = _render_image_crop(page, box)
        images.append(
            ImageElement(
                id=f"page-{page_number}-image-{index}",
                bbox=box,
                width_px=width_px,
                height_px=height_px,
                role=role,
                mime_type="image/png" if content_base64 else None,
                content_base64=content_base64,
            )
        )
    return images


def _decorations(page: Any, page_number: int, page_height: float) -> list[Decoration]:
    decorations: list[Decoration] = []
    sources = (("rectangle", page.rects), ("line", page.lines), ("curve", page.curves))
    index = 1
    for kind, items in sources:
        for item in items:
            decorations.append(
                Decoration(
                    id=f"page-{page_number}-decoration-{index}",
                    bbox=_bbox(item, page_height),
                    kind=kind,
                    fill_color=_colour(item.get("non_stroking_color"))
                    if item.get("fill")
                    else None,
                    stroke_color=_colour(item.get("stroking_color"))
                    if item.get("stroke")
                    else None,
                    stroke_width=float(item.get("linewidth") or 0.0),
                )
            )
            index += 1
    return decorations


def extract_pdf(content: bytes) -> ExtractedDocument:
    pages: list[ExtractedPage] = []
    signals: list[PageSignals] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            width = float(page.width)
            height = float(page.height)
            images = _images(page, page_number, height)
            icons = _vector_icons(page, page_number, height, images)
            page_glyphs = _glyphs(page.chars, height)
            lines = _group_glyphs_into_lines(page_glyphs)
            blocks = _group_lines_into_blocks(lines, page_number)
            vector_backgrounds = _vector_backgrounds(
                page, page_number, height, images, blocks, page_glyphs
            )
            all_images = images + icons + vector_backgrounds
            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    width_pt=width,
                    height_pt=height,
                    blocks=blocks,
                    images=all_images,
                    decorations=_decorations(page, page_number, height),
                )
            )
            page_area = max(width * height, 1.0)
            signals.append(
                PageSignals(
                    text_character_count=sum(len(glyph.text.strip()) for glyph in page_glyphs),
                    image_count=len(images),
                    largest_image_coverage=max(
                        (image.bbox.width * image.bbox.height / page_area for image in images),
                        default=0.0,
                    ),
                )
            )

    source_type = classify_pdf(signals)
    warnings: list[str] = []
    if source_type == "scanned":
        warnings.append("Scanned PDFs are outside the MVP scope; OCR was not performed.")
    elif source_type == "hybrid":
        warnings.append("Hybrid PDF detected; image-only content may not be editable.")
    return ExtractedDocument(source_type=source_type, pages=pages, warnings=warnings)
