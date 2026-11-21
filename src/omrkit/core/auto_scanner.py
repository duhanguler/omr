"""Zero-template automatic scanning via embedded QR template + student metadata discovery."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from omrkit.core.scanner import OMRScanner, inject_qr_student_metadata
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import get_sheet_presets
from omrkit.io.loader import LoadedPage, load_bytes, load_document
from omrkit.models.scan import SheetResult
from omrkit.models.template import Template
from omrkit.vision.qr import SheetQRPayload, detect_sheet_qr_payload
from omrkit.vision.registration import RegistrationError, register_sheet


@lru_cache(maxsize=1)
def _builtin_preset_templates() -> dict[str, Template]:
    gen = SheetGenerator()
    return {pid: gen.generate(spec).template for pid, spec in get_sheet_presets().items()}


def resolve_template_payload_for_image(
    image_bgr: np.ndarray,
    extra_templates: dict[str, Template] | None = None,
) -> tuple[Template, SheetQRPayload] | None:
    """Detect an OMRKit v2/v3 QR badge and resolve its matching Template + SheetQRPayload."""
    registry: dict[str, Template] = dict(_builtin_preset_templates())
    if extra_templates:
        registry.update(extra_templates)

    payload = detect_sheet_qr_payload(image_bgr)
    if payload is not None and payload.preset_id in registry:
        return registry[payload.preset_id], payload

    # Fallback: use standard A4 ArUco corner rectification to flatten perspective, then read QR
    fallback_template = registry.get("standard_mcq_40")
    if fallback_template is not None:
        try:
            reg = register_sheet(image_bgr, fallback_template)
            wh, ww = reg.warped_bgr.shape[:2]
            # Try upper-right header ROI first (fast & zoomed) then full rectified image
            qr_roi = reg.warped_bgr[0 : round(wh * 0.22), round(ww * 0.65) : ww]
            for view in (qr_roi, reg.warped_bgr):
                payload = detect_sheet_qr_payload(view)
                if payload is not None and payload.preset_id in registry:
                    return registry[payload.preset_id], payload
        except RegistrationError:
            pass

    return None


def resolve_template_for_image(
    image_bgr: np.ndarray,
    extra_templates: dict[str, Template] | None = None,
) -> tuple[Template, str] | None:
    """Detect an OMRKit sheet's embedded QR template ID and resolve its matching Template."""
    resolved = resolve_template_payload_for_image(image_bgr, extra_templates=extra_templates)
    if resolved is None:
        return None
    template, payload = resolved
    return template, payload.preset_id


def scan_page_auto(
    page: LoadedPage,
    extra_templates: dict[str, Template] | None = None,
    save_overlay_dir: str | Path | None = None,
) -> tuple[SheetResult, np.ndarray | None]:
    """Automatically identify a page's template (and v3 student metadata) via QR and scan it."""
    resolved = resolve_template_payload_for_image(page.image_bgr, extra_templates=extra_templates)
    if resolved is None:
        stem = Path(page.source_name).stem
        sheet_id = f"{stem}_p{page.page_index + 1}" if page.page_index > 0 else stem
        return (
            SheetResult(
                sheet_id=sheet_id,
                source_file=page.source_name,
                page_index=page.page_index,
                template_name="auto",
                overall_confidence=0.0,
                registration_method="qr_auto",
                registration_score=0.0,
                error=(
                    "Auto-template detection failed: no recognized OMRKit QR code found. "
                    "Provide an explicit template.json for custom sheets."
                ),
            ),
            None,
        )

    template, payload = resolved
    result, warped = OMRScanner(template).scan_page(page, save_overlay_dir=save_overlay_dir)
    if result.error is None and payload.has_student_metadata:
        inject_qr_student_metadata(result, payload)
    return result, warped


def scan_image_auto(
    image_bgr: np.ndarray,
    source_name: str = "image.png",
    extra_templates: dict[str, Template] | None = None,
) -> tuple[SheetResult, np.ndarray | None]:
    """Auto-detect template via QR code and scan an in-memory BGR image."""
    h, w = image_bgr.shape[:2]
    page = LoadedPage(
        source_name=source_name,
        page_index=0,
        image_bgr=image_bgr,
        original_width=w,
        original_height=h,
    )
    return scan_page_auto(page, extra_templates=extra_templates)


def scan_bytes_auto(
    data: bytes,
    filename: str,
    dpi: int = 200,
    extra_templates: dict[str, Template] | None = None,
    max_pages: int | None = None,
) -> list[tuple[SheetResult, np.ndarray | None]]:
    """Auto-detect template per page and scan uploaded image or multi-page PDF bytes."""
    pages = load_bytes(data, filename=filename, dpi=dpi, max_pages=max_pages)
    return [scan_page_auto(p, extra_templates=extra_templates) for p in pages]


def scan_file_auto(
    path: str | Path,
    dpi: int = 200,
    extra_templates: dict[str, Template] | None = None,
    save_overlay_dir: str | Path | None = None,
) -> list[SheetResult]:
    """Auto-detect template per page and scan an image or multi-page PDF on disk."""
    pages = load_document(path, dpi=dpi)
    return [
        scan_page_auto(p, extra_templates=extra_templates, save_overlay_dir=save_overlay_dir)[0]
        for p in pages
    ]
