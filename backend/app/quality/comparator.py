import io
import re
from collections import Counter
from collections.abc import Callable

from docx import Document
from docx.oxml.ns import qn
from PIL import Image, ImageChops, ImageStat

from app.quality.models import QualityMetrics, QualityReport
from app.quality.renderer import RenderedPage

_WORD = re.compile(r"\w+", re.UNICODE)


def _normalised_words(value: str) -> Counter[str]:
    return Counter(_WORD.findall(value.casefold()))


def _text_accuracy(source: str, result: str) -> float:
    source_words = _normalised_words(source)
    result_words = _normalised_words(result)
    if not source_words and not result_words:
        return 1.0
    overlap = sum((source_words & result_words).values())
    precision = overlap / max(sum(result_words.values()), 1)
    recall = overlap / max(sum(source_words.values()), 1)
    return 2 * precision * recall / max(precision + recall, 1e-9)


def _load_aligned(source: RenderedPage, result: RenderedPage) -> tuple[Image.Image, Image.Image]:
    source_image = Image.open(io.BytesIO(source.png)).convert("RGB")
    result_image = Image.open(io.BytesIO(result.png)).convert("RGB")
    if result_image.size != source_image.size:
        result_image = result_image.resize(source_image.size, Image.Resampling.LANCZOS)
    return source_image, result_image


def _ink_mask(image: Image.Image) -> Image.Image:
    return image.convert("L").point(lambda value: 255 if value < 245 else 0).convert("1")


def _page_visual_similarity(source: RenderedPage, result: RenderedPage) -> float:
    source_image, result_image = _load_aligned(source, result)
    difference = ImageChops.difference(source_image, result_image)
    mean_difference = sum(ImageStat.Stat(difference).mean) / (3 * 255)
    pixel_score = 1 - mean_difference

    source_mask = _ink_mask(source_image)
    result_mask = _ink_mask(result_image)
    intersection = ImageChops.logical_and(source_mask, result_mask).histogram()[255]
    union = ImageChops.logical_or(source_mask, result_mask).histogram()[255]
    ink_score = intersection / union if union else 1.0
    return max(0.0, min(1.0, pixel_score * 0.35 + ink_score * 0.65))


def _page_layout_similarity(source: RenderedPage, result: RenderedPage) -> float:
    source_image, result_image = _load_aligned(source, result)
    source_grid = (
        _ink_mask(source_image)
        .convert("L")
        .resize((48, 64), Image.Resampling.BOX)
        .point(lambda value: 255 if value > 6 else 0)
        .convert("1")
    )
    result_grid = (
        _ink_mask(result_image)
        .convert("L")
        .resize((48, 64), Image.Resampling.BOX)
        .point(lambda value: 255 if value > 6 else 0)
        .convert("1")
    )
    intersection = ImageChops.logical_and(source_grid, result_grid).histogram()[255]
    union = ImageChops.logical_or(source_grid, result_grid).histogram()[255]
    return intersection / union if union else 1.0


def _page_average(
    source_pages: list[RenderedPage],
    result_pages: list[RenderedPage],
    comparator: Callable[[RenderedPage, RenderedPage], float],
) -> float:
    page_count = max(len(source_pages), len(result_pages), 1)
    scores = [
        comparator(source, result)
        for source, result in zip(source_pages, result_pages, strict=False)
    ]
    scores.extend(0.0 for _ in range(page_count - len(scores)))
    return sum(scores) / page_count


def extract_docx_text(content: bytes) -> str:
    document = Document(io.BytesIO(content))
    values = [node.text for node in document.element.body.iter(qn("w:t")) if node.text]
    for section in document.sections:
        for container in (section.header, section.footer):
            values.extend(paragraph.text for paragraph in container.paragraphs if paragraph.text)
    return "\n".join(values)


def _round_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)) * 100, 1)


def compare_conversion(
    source_pages: list[RenderedPage],
    result_pages: list[RenderedPage],
    *,
    source_text: str,
    result_text: str,
) -> QualityReport:
    visual = _page_average(source_pages, result_pages, _page_visual_similarity)
    layout = _page_average(source_pages, result_pages, _page_layout_similarity)
    text = _text_accuracy(source_text, result_text)
    page_count = min(len(source_pages), len(result_pages)) / max(
        len(source_pages), len(result_pages), 1
    )
    overall = visual * 0.4 + text * 0.35 + layout * 0.2 + page_count * 0.05

    differences: list[str] = []
    if len(source_pages) != len(result_pages):
        differences.append(
            f"Numero di pagine diverso: originale {len(source_pages)}, DOCX {len(result_pages)}."
        )
    if text < 0.99:
        differences.append("Una parte del testo risulta mancante, duplicata o modificata.")
    if visual < 0.85:
        differences.append(
            "Colori, immagini o decorazioni differiscono visibilmente dall'originale."
        )
    if layout < 0.9:
        differences.append("Posizione e spaziatura dei blocchi differiscono dall'originale.")
    if not differences:
        differences.append("Non sono state rilevate differenze significative.")

    if overall >= 0.9:
        rating = "excellent"
    elif overall >= 0.75:
        rating = "good"
    elif overall >= 0.55:
        rating = "fair"
    else:
        rating = "poor"
    return QualityReport(
        overall_score=_round_score(overall),
        rating=rating,
        metrics=QualityMetrics(
            visual_similarity=_round_score(visual),
            text_accuracy=_round_score(text),
            layout_similarity=_round_score(layout),
            page_count_match=_round_score(page_count),
        ),
        differences=differences,
    )
