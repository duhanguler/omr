"""Unified document loader for images (with EXIF auto-orientation) and multi-page PDFs."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageOps

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
)
PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})
SUPPORTED_EXTENSIONS: frozenset[str] = IMAGE_EXTENSIONS | PDF_EXTENSIONS


class DocumentLoadError(RuntimeError):
    """Raised when an input image or PDF cannot be opened or decoded."""


@dataclass(slots=True)
class LoadedPage:
    """A single decoded document page in standard BGR OpenCV format."""

    source_name: str
    page_index: int
    image_bgr: np.ndarray
    original_width: int
    original_height: int


def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    """Apply EXIF orientation and convert a PIL Image to an OpenCV BGR array."""
    oriented = ImageOps.exif_transpose(img)
    rgb = oriented.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _render_pdf_document(
    pdf_doc: pdfium.PdfDocument,
    source_name: str,
    dpi: int = 200,
    max_pages: int | None = None,
) -> list[LoadedPage]:
    scale = dpi / 72.0
    pages: list[LoadedPage] = []
    try:
        page_count = len(pdf_doc)
        if max_pages is not None and page_count > max_pages:
            raise DocumentLoadError(
                f"PDF '{source_name}' has {page_count} pages, exceeding the configured limit of {max_pages}."
            )
        for idx in range(page_count):
            page = pdf_doc[idx]
            try:
                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil()
                bgr = _pil_to_bgr(pil_img)
                h, w = bgr.shape[:2]
                pages.append(
                    LoadedPage(
                        source_name=source_name,
                        page_index=idx,
                        image_bgr=bgr,
                        original_width=w,
                        original_height=h,
                    )
                )
            finally:
                page.close()
    finally:
        pdf_doc.close()
    return pages


def load_document(
    source: str | Path,
    dpi: int = 200,
    max_pages: int | None = None,
) -> list[LoadedPage]:
    """Load an image file or multi-page PDF into a list of EXIF-oriented BGR pages."""
    path = Path(source)
    if not path.exists():
        raise DocumentLoadError(f"Input file does not exist: '{path}'")
    if not path.is_file():
        raise DocumentLoadError(f"Expected a file path, got directory: '{path}'")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentLoadError(
            f"Unsupported file format '{ext}' for '{path.name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext in PDF_EXTENSIONS:
        try:
            pdf_doc = pdfium.PdfDocument(str(path))
            return _render_pdf_document(
                pdf_doc, source_name=path.name, dpi=dpi, max_pages=max_pages
            )
        except DocumentLoadError:
            raise
        except Exception as exc:
            raise DocumentLoadError(f"Failed to decode PDF '{path.name}': {exc}") from exc

    try:
        with Image.open(path) as pil_img:
            bgr = _pil_to_bgr(pil_img)
    except Exception as exc:
        raise DocumentLoadError(f"Failed to decode image '{path.name}': {exc}") from exc

    h, w = bgr.shape[:2]
    return [
        LoadedPage(
            source_name=path.name,
            page_index=0,
            image_bgr=bgr,
            original_width=w,
            original_height=h,
        )
    ]


def load_bytes(
    data: bytes,
    filename: str,
    dpi: int = 200,
    max_pages: int | None = None,
) -> list[LoadedPage]:
    """Decode uploaded image or PDF bytes directly in memory."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentLoadError(
            f"Unsupported file format '{ext}' for '{filename}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext in PDF_EXTENSIONS:
        try:
            pdf_doc = pdfium.PdfDocument(data)
            return _render_pdf_document(pdf_doc, source_name=filename, dpi=dpi, max_pages=max_pages)
        except DocumentLoadError:
            raise
        except Exception as exc:
            raise DocumentLoadError(f"Failed to decode PDF '{filename}': {exc}") from exc

    try:
        with Image.open(io.BytesIO(data)) as pil_img:
            bgr = _pil_to_bgr(pil_img)
    except Exception as exc:
        raise DocumentLoadError(f"Failed to decode image '{filename}': {exc}") from exc

    h, w = bgr.shape[:2]
    return [
        LoadedPage(
            source_name=filename,
            page_index=0,
            image_bgr=bgr,
            original_width=w,
            original_height=h,
        )
    ]


def discover_documents(path: str | Path, recursive: bool = False) -> list[Path]:
    """Discover all supported image and PDF files from a file or directory path."""
    target = Path(path)
    if not target.exists():
        raise DocumentLoadError(f"Input path does not exist: '{target}'")
    if target.is_file():
        if target.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise DocumentLoadError(f"Unsupported file type: '{target}'")
        return [target]

    iterator = target.rglob("*") if recursive else target.iterdir()
    files = [p for p in iterator if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    return sorted(files)


def strip_exif_and_save(
    src: str | Path,
    dst: str | Path,
    quality: int = 92,
    max_dimension: int | None = None,
) -> tuple[int, int]:
    """Apply EXIF orientation permanently to pixels and write a clean metadata-free image."""
    src_path = Path(src)
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src_path) as img:
        oriented = ImageOps.exif_transpose(img).convert("RGB")
        if max_dimension is not None:
            oriented.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        # Re-create pixel-only image to guarantee zero EXIF/GPS/ICC leftovers
        clean = Image.new("RGB", oriented.size)
        clean.paste(oriented)
        if dst_path.suffix.lower() in {".jpg", ".jpeg"}:
            clean.save(dst_path, quality=quality, optimize=True)
        else:
            clean.save(dst_path)
        return clean.size
