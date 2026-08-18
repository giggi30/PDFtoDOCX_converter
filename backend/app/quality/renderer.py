import io
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pypdfium2


class RenderingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    png: bytes
    width_px: int
    height_px: int


def render_pdf(content: bytes, dpi: int = 96) -> list[RenderedPage]:
    scale = dpi / 72
    pages: list[RenderedPage] = []
    document = pypdfium2.PdfDocument(content)
    try:
        for index in range(len(document)):
            page = document[index]
            try:
                image = page.render(scale=scale).to_pil().convert("RGB")
                stream = io.BytesIO()
                image.save(stream, format="PNG", optimize=True)
                pages.append(
                    RenderedPage(
                        page_number=index + 1,
                        png=stream.getvalue(),
                        width_px=image.width,
                        height_px=image.height,
                    )
                )
            finally:
                page.close()
    finally:
        document.close()
    return pages


def render_docx(
    content: bytes,
    *,
    dpi: int = 96,
    libreoffice_binary: str = "soffice",
    timeout_seconds: int = 30,
) -> list[RenderedPage]:
    executable = shutil.which(libreoffice_binary)
    if executable is None:
        raise RenderingError("LibreOffice is unavailable")

    with tempfile.TemporaryDirectory(prefix="pdf-to-docx-render-") as temporary:
        root = Path(temporary)
        input_path = root / "document.docx"
        output_path = root / "document.pdf"
        profile_path = root / "libreoffice-profile"
        home_path = root / "home"
        profile_path.mkdir()
        home_path.mkdir()
        input_path.write_bytes(content)
        environment = os.environ.copy()
        environment["HOME"] = str(home_path)
        try:
            completed = subprocess.run(
                [
                    executable,
                    f"-env:UserInstallation={profile_path.as_uri()}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(root),
                    str(input_path),
                ],
                check=False,
                capture_output=True,
                timeout=timeout_seconds,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderingError("LibreOffice rendering timed out") from exc
        if completed.returncode != 0 or not output_path.is_file():
            raise RenderingError("LibreOffice could not render the generated DOCX")
        return render_pdf(output_path.read_bytes(), dpi=dpi)
