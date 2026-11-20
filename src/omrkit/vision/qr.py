"""Embedded QR code encoding and automatic template discovery for OMRKit sheets."""

from __future__ import annotations

import cv2
import numpy as np

from omrkit.vision.preprocess import ensure_grayscale

QR_PREFIX = "OMRKIT:v2:"


def encode_sheet_qr_payload(preset_id: str) -> str:
    """Build a compact canonical QR payload identifying an OMRKit sheet layout."""
    return f"{QR_PREFIX}{preset_id.strip()}"


def parse_sheet_qr_payload(raw_text: str) -> str | None:
    """Extract the preset/template ID from a decoded QR payload, or None if unrecognized."""
    cleaned = raw_text.strip()
    if not cleaned.startswith(QR_PREFIX):
        return None
    preset_id = cleaned[len(QR_PREFIX) :].strip()
    return preset_id or None


def render_qr_matrix(payload: str, pixel_size: int = 220) -> np.ndarray:
    """Generate a crisp binary QR code image with a white quiet zone using OpenCV."""
    encoder = cv2.QRCodeEncoder_create()  # type: ignore[attr-defined]
    matrix = encoder.encode(payload)
    scaled = cv2.resize(matrix, (pixel_size, pixel_size), interpolation=cv2.INTER_NEAREST)
    pad = max(12, pixel_size // 10)
    bordered: np.ndarray = cv2.copyMakeBorder(
        scaled, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255
    )
    return bordered


def detect_sheet_qr(image_bgr: np.ndarray) -> str | None:
    """Detect and decode an OMRKit template ID QR code from an image (any orientation)."""
    detector = cv2.QRCodeDetector()
    gray = ensure_grayscale(image_bgr)

    candidates: list[np.ndarray] = [gray]
    # Add CLAHE contrast-boosted version for shadowed phone captures
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    candidates.append(clahe.apply(gray))

    # Downscaled variant helps when QR modules have subtle camera noise at huge resolutions
    h, w = gray.shape[:2]
    if max(h, w) > 1800:
        scale = 1400.0 / float(max(h, w))
        candidates.append(
            cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        )

    for img in candidates:
        text, _, _ = detector.detectAndDecode(img)
        if text:
            parsed = parse_sheet_qr_payload(text)
            if parsed is not None:
                return parsed

        # Fallback: decodeMulti handles sheets where corner markers confuse single-QR finder
        ok, decoded_list, _, _ = detector.detectAndDecodeMulti(img)
        if ok and decoded_list:
            for item in decoded_list:
                parsed = parse_sheet_qr_payload(item)
                if parsed is not None:
                    return parsed

    # Focused high-contrast upscaled pass on small crops (e.g., rectified QR badge)
    if max(h, w) <= 600:
        up = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        _, otsu = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for img in (up, otsu):
            text, _, _ = detector.detectAndDecode(img)
            if text:
                parsed = parse_sheet_qr_payload(text)
                if parsed is not None:
                    return parsed

    return None
