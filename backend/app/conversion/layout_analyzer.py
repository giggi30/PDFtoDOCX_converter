from dataclasses import dataclass

from app.conversion.models import (
    BoundingBox,
    DocumentModel,
    ExtractedDocument,
    ExtractedPage,
    PageModel,
    Region,
    RegionType,
    TextBlock,
)


@dataclass(frozen=True)
class _ColumnSplit:
    boundary: float
    left: list[TextBlock]
    right: list[TextBlock]
    excluded: list[TextBlock]


def _reading_order(blocks: list[TextBlock]) -> list[TextBlock]:
    return sorted(blocks, key=lambda block: (round(block.bbox.y0, 1), block.bbox.x0))


def _two_cluster_centres(values: list[float]) -> tuple[float, float, list[int]]:
    left_centre = min(values)
    right_centre = max(values)
    assignments = [0 for _ in values]
    for _ in range(12):
        assignments = [
            0 if abs(value - left_centre) <= abs(value - right_centre) else 1 for value in values
        ]
        left_values = [
            value for value, group in zip(values, assignments, strict=True) if group == 0
        ]
        right_values = [
            value for value, group in zip(values, assignments, strict=True) if group == 1
        ]
        if not left_values or not right_values:
            break
        new_left = sum(left_values) / len(left_values)
        new_right = sum(right_values) / len(right_values)
        if abs(new_left - left_centre) < 0.1 and abs(new_right - right_centre) < 0.1:
            left_centre, right_centre = new_left, new_right
            break
        left_centre, right_centre = new_left, new_right
    return left_centre, right_centre, assignments


def _find_columns(page: ExtractedPage) -> _ColumnSplit | None:
    if len(page.blocks) < 4:
        return None
    sizes = sorted(block.style.font_size for block in page.blocks)
    median_size = sizes[len(sizes) // 2]
    excluded = [
        block
        for block in page.blocks
        if block.bbox.y0 < page.height_pt * 0.16 and block.style.font_size >= median_size * 1.5
    ]
    candidates = [
        block
        for block in page.blocks
        if block not in excluded and block.bbox.width <= page.width_pt * 0.58
    ]
    if len(candidates) < 4:
        return None
    centres = [(block.bbox.x0 + block.bbox.x1) / 2 for block in candidates]
    left_centre, right_centre, assignments = _two_cluster_centres(centres)
    if right_centre - left_centre < page.width_pt * 0.22:
        return None
    left = [block for block, group in zip(candidates, assignments, strict=True) if group == 0]
    right = [block for block, group in zip(candidates, assignments, strict=True) if group == 1]
    if len(left) < 2 or len(right) < 2:
        return None

    left_top = min(block.bbox.y0 for block in left)
    right_top = min(block.bbox.y0 for block in right)
    left_bottom = max(block.bbox.y1 for block in left)
    right_bottom = max(block.bbox.y1 for block in right)
    shared_height = max(0.0, min(left_bottom, right_bottom) - max(left_top, right_top))
    shorter_height = max(1.0, min(left_bottom - left_top, right_bottom - right_top))
    if shared_height / shorter_height < 0.3:
        return None
    if abs(left_top - right_top) > page.height_pt * 0.2:
        return None
    boundary = (left_centre + right_centre) / 2
    crossing = [
        block
        for block in page.blocks
        if block not in candidates
        and block not in excluded
        and block.bbox.x0 < boundary < block.bbox.x1
    ]
    if len(crossing) > max(1, len(page.blocks) // 4):
        return None
    excluded.extend(
        block for block in page.blocks if block not in candidates and block not in excluded
    )
    return _ColumnSplit(boundary=boundary, left=left, right=right, excluded=excluded)


def _has_sidebar_background(page: ExtractedPage, left_side: bool, boundary: float) -> bool:
    for decoration in page.decorations:
        if decoration.kind != "rectangle" or decoration.fill_color is None:
            continue
        tall = decoration.bbox.height >= page.height_pt * 0.45
        if left_side:
            covers_side = (
                decoration.bbox.x0 <= page.width_pt * 0.05 and decoration.bbox.x1 <= boundary * 1.2
            )
        else:
            covers_side = (
                decoration.bbox.x1 >= page.width_pt * 0.95
                and decoration.bbox.x0 >= boundary - (page.width_pt - boundary) * 0.2
            )
        if tall and covers_side:
            return True
    return False


def _region(
    region_type: RegionType,
    blocks: list[TextBlock],
    page: ExtractedPage,
    bbox: BoundingBox | None = None,
) -> Region:
    ordered = _reading_order(blocks)
    region_bbox = bbox or (
        BoundingBox.enclosing([block.bbox for block in ordered])
        if ordered
        else BoundingBox(x0=0, y0=0, x1=page.width_pt, y1=page.height_pt)
    )
    return Region(type=region_type, bbox=region_bbox, blocks=ordered)


def _visible_coloured_rectangles(page: ExtractedPage) -> list[BoundingBox]:
    return [
        decoration.bbox
        for decoration in page.decorations
        if decoration.kind == "rectangle"
        and decoration.fill_color not in {None, "#000000", "#FFFFFF"}
    ]


def _blocks_with_inferred_lists(
    page: ExtractedPage, blocks: list[TextBlock]
) -> list[TextBlock]:
    result: list[TextBlock] = []
    for block in blocks:
        has_vector_bullet = any(
            decoration.kind == "curve"
            and decoration.fill_color not in {None, "#FFFFFF"}
            and max(decoration.bbox.width, decoration.bbox.height) <= 8
            # A bullet sits immediately before its text.  A wider tolerance
            # mistakes details inside contact icons for bullets.
            and block.bbox.x0 - 12 <= decoration.bbox.x1 <= block.bbox.x0
            and block.bbox.y0 - 3
            <= (decoration.bbox.y0 + decoration.bbox.y1) / 2
            <= block.bbox.y1 + 3
            for decoration in page.decorations
        )
        if has_vector_bullet and block.block_type != "list_item":
            result.append(block.model_copy(update={"block_type": "list_item"}))
        else:
            result.append(block)
    return result


def _hero_blocks(
    page: ExtractedPage,
    hero_bbox: BoundingBox,
    available: list[TextBlock],
) -> list[TextBlock]:
    overlapping_images = [
        image
        for image in page.images
        if image.bbox.y0 <= hero_bbox.y1 and image.bbox.y1 >= hero_bbox.y0
    ]
    image_bottom = max((image.bbox.y1 for image in overlapping_images), default=hero_bbox.y1)
    content_bottom = min(max(hero_bbox.y1, image_bottom), page.height_pt * 0.35)
    return [
        block
        for block in available
        if hero_bbox.y0 - 2 <= (block.bbox.y0 + block.bbox.y1) / 2 <= content_bottom + 2
    ]


def _zoned_regions(page: ExtractedPage) -> list[Region] | None:
    rectangles = _visible_coloured_rectangles(page)
    hero_bbox = next(
        (
            bbox
            for bbox in rectangles
            if bbox.width >= page.width_pt * 0.75
            and bbox.height >= page.height_pt * 0.08
            and bbox.height <= page.height_pt * 0.3
            and bbox.y0 <= page.height_pt * 0.05
        ),
        None,
    )
    card_bbox = next(
        (
            bbox
            for bbox in rectangles
            if page.width_pt * 0.25 <= bbox.width <= page.width_pt * 0.65
            and page.height_pt * 0.08 <= bbox.height <= page.height_pt * 0.3
            and bbox.y0 >= page.height_pt * 0.55
        ),
        None,
    )
    if hero_bbox is None and card_bbox is None:
        return None

    available = list(page.blocks)
    regions: list[Region] = []
    if hero_bbox is not None:
        hero_blocks = _hero_blocks(page, hero_bbox, available)
        available = [block for block in available if block not in hero_blocks]
        regions.append(_region("hero", hero_blocks, page, hero_bbox))

    if card_bbox is not None:
        card_blocks = [
            block
            for block in available
            if card_bbox.x0 - 8 <= (block.bbox.x0 + block.bbox.x1) / 2 <= card_bbox.x1 + 8
            and card_bbox.y0 - 8 <= (block.bbox.y0 + block.bbox.y1) / 2 <= card_bbox.y1 + 8
        ]
        available = [block for block in available if block not in card_blocks]
    else:
        card_blocks = []

    remaining_page = page.model_copy(update={"blocks": available})
    split = _find_columns(remaining_page)
    if split is None:
        regions.append(_region("main", _blocks_with_inferred_lists(page, available), page))
    else:
        left = list(split.left)
        right = list(split.right)
        for block in split.excluded:
            centre = (block.bbox.x0 + block.bbox.x1) / 2
            (left if centre < split.boundary else right).append(block)
        regions.extend(
            [
                _region("column", _blocks_with_inferred_lists(page, left), page),
                _region("column", _blocks_with_inferred_lists(page, right), page),
            ]
        )
    if card_bbox is not None:
        regions.append(
            _region("card", _blocks_with_inferred_lists(page, card_blocks), page, card_bbox)
        )
    return regions


def _regions_for(page: ExtractedPage) -> list[Region]:
    if not page.blocks:
        return [_region("main", [], page)]
    zoned = _zoned_regions(page)
    if zoned is not None:
        return zoned
    split = _find_columns(page)
    if split is None:
        return [_region("main", page.blocks, page)]

    left_is_sidebar = _has_sidebar_background(page, True, split.boundary) or (
        split.boundary <= page.width_pt * 0.36
    )
    right_is_sidebar = _has_sidebar_background(page, False, split.boundary) or (
        page.width_pt - split.boundary <= page.width_pt * 0.36
    )

    if left_is_sidebar or right_is_sidebar:
        left = list(split.left)
        right = list(split.right)
        for block in split.excluded:
            centre = (block.bbox.x0 + block.bbox.x1) / 2
            (left if centre < split.boundary else right).append(block)
        left_type: RegionType = "sidebar" if left_is_sidebar else "main"
        right_type: RegionType = "sidebar" if right_is_sidebar else "main"
        return [_region(left_type, left, page), _region(right_type, right, page)]

    header = [block for block in split.excluded if block.bbox.y0 < page.height_pt * 0.2]
    footer = [
        block
        for block in split.excluded
        if block.bbox.y1 > page.height_pt * 0.9 and block not in header
    ]
    remaining = [block for block in split.excluded if block not in header and block not in footer]
    left = list(split.left)
    right = list(split.right)
    for block in remaining:
        centre = (block.bbox.x0 + block.bbox.x1) / 2
        (left if centre < split.boundary else right).append(block)

    regions: list[Region] = []
    if header:
        regions.append(_region("header", header, page))
    regions.extend([_region("column", left, page), _region("column", right, page)])
    if footer:
        regions.append(_region("footer", footer, page))
    return regions


def analyze_layout(extracted: ExtractedDocument) -> DocumentModel:
    pages = [
        PageModel(
            page_number=page.page_number,
            width_pt=page.width_pt,
            height_pt=page.height_pt,
            regions=_regions_for(page),
            images=page.images,
            decorations=page.decorations,
        )
        for page in extracted.pages
    ]
    return DocumentModel(
        source_type=extracted.source_type,
        pages=pages,
        warnings=extracted.warnings,
    )
