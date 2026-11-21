"""Automatic TrueType Unicode font discovery for crisp multilingual ReportLab PDFs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_TURKISH_FALLBACK_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

_FONT_CANDIDATE_PAIRS: tuple[tuple[str, str], ...] = (
    # Debian / Ubuntu / Docker (fonts-liberation)
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ),
    # DejaVu Sans (Linux)
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    # macOS
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    # Windows
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
)


@dataclass(frozen=True, slots=True)
class PdfFontPair:
    """Resolved ReportLab font family names and Unicode capability flag."""

    regular: str
    bold: str
    unicode_ready: bool

    def format_text(self, text: str) -> str:
        """Return native Unicode text when TTF fonts are registered, else safe ASCII."""
        if self.unicode_ready:
            return text
        return text.translate(_TURKISH_FALLBACK_MAP).encode("latin-1", "replace").decode("latin-1")


@lru_cache(maxsize=1)
def get_pdf_fonts() -> PdfFontPair:
    """Discover and register a Unicode-capable TrueType sans-serif pair once per process."""
    candidates: list[tuple[Path, Path]] = []
    custom_dir = os.environ.get("OMRKIT_PDF_FONT_DIR")
    if custom_dir:
        base = Path(custom_dir)
        for reg_name, bold_name in (
            ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
            ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
        ):
            candidates.append((base / reg_name, base / bold_name))

    candidates.extend((Path(r), Path(b)) for r, b in _FONT_CANDIDATE_PAIRS)

    for reg_path, bold_path in candidates:
        if reg_path.is_file() and bold_path.is_file():
            try:
                registered = set(pdfmetrics.getRegisteredFontNames())
                if "OMRKitSans" not in registered:
                    pdfmetrics.registerFont(TTFont("OMRKitSans", str(reg_path)))
                if "OMRKitSans-Bold" not in registered:
                    pdfmetrics.registerFont(TTFont("OMRKitSans-Bold", str(bold_path)))
                return PdfFontPair(
                    regular="OMRKitSans",
                    bold="OMRKitSans-Bold",
                    unicode_ready=True,
                )
            except Exception:
                continue

    return PdfFontPair(regular="Helvetica", bold="Helvetica-Bold", unicode_ready=False)
