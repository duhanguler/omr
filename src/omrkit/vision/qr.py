"""Embedded QR code encoding and automatic template + student metadata discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, unquote

import cv2
import numpy as np

from omrkit.vision.preprocess import ensure_grayscale

QR_PREFIX = "OMRKIT:v2:"
QR_V3_PREFIX = "OMRKIT:v3:"


@dataclass(frozen=True, slots=True)
class SheetQRPayload:
    """Decoded OMRKit QR metadata (supports both v2 preset-only and v3 student packets)."""

    preset_id: str
    student_id: str | None = None
    student_name: str | None = None
    classroom: str | None = None
    booklet: str | None = None
    email: str | None = None
    version: Literal["v2", "v3"] = "v2"

    @property
    def has_student_metadata(self) -> bool:
        return any(
            val
            for val in (
                self.student_id,
                self.student_name,
                self.classroom,
                self.booklet,
                self.email,
            )
        )


def encode_sheet_qr_payload(
    preset_id: str,
    *,
    student_id: str | None = None,
    student_name: str | None = None,
    classroom: str | None = None,
    booklet: str | None = None,
    email: str | None = None,
) -> str:
    """Build a compact canonical QR payload identifying an OMRKit sheet layout.

    Emits backward-compatible ``OMRKIT:v2:<preset_id>`` when no student fields are provided,
    and compact ``OMRKIT:v3:<preset_id>|sid=...|n=...|c=...|b=...|e=...`` for personalized
    roster sheets.
    """
    pid = preset_id.strip()
    parts: list[str] = []
    if student_id and student_id.strip():
        parts.append(f"sid={quote(student_id.strip()[:24], safe='')}")
    if student_name and student_name.strip():
        parts.append(f"n={quote(student_name.strip()[:42], safe='')}")
    if classroom and classroom.strip():
        parts.append(f"c={quote(classroom.strip()[:20], safe='')}")
    if booklet and booklet.strip():
        parts.append(f"b={quote(booklet.strip()[:8].upper(), safe='')}")
    if email and email.strip():
        parts.append(f"e={quote(email.strip()[:48], safe='@._-')}")

    if not parts:
        return f"{QR_PREFIX}{pid}"
    return f"{QR_V3_PREFIX}{pid}|" + "|".join(parts)


def parse_sheet_qr_details(raw_text: str) -> SheetQRPayload | None:
    """Parse an ``OMRKIT:v2`` or ``OMRKIT:v3`` QR payload into a structured SheetQRPayload."""
    cleaned = raw_text.strip()
    if cleaned.startswith(QR_PREFIX):
        preset_id = cleaned[len(QR_PREFIX) :].strip()
        if not preset_id:
            return None
        return SheetQRPayload(preset_id=preset_id, version="v2")

    if cleaned.startswith(QR_V3_PREFIX):
        body = cleaned[len(QR_V3_PREFIX) :].strip()
        if not body:
            return None
        segments = body.split("|")
        preset_id = segments[0].strip()
        if not preset_id:
            return None
        meta: dict[str, str] = {}
        for seg in segments[1:]:
            if "=" not in seg:
                continue
            k, v = seg.split("=", 1)
            key = k.strip().lower()
            val = unquote(v.strip())
            if val:
                meta[key] = val
        return SheetQRPayload(
            preset_id=preset_id,
            student_id=meta.get("sid"),
            student_name=meta.get("n"),
            classroom=meta.get("c"),
            booklet=meta.get("b"),
            email=meta.get("e"),
            version="v3",
        )

    return None


def parse_sheet_qr_payload(raw_text: str) -> str | None:
    """Extract the preset/template ID from a decoded QR payload, or None if unrecognized."""
    details = parse_sheet_qr_details(raw_text)
    return details.preset_id if details is not None else None


def render_qr_matrix(payload: str, pixel_size: int = 240) -> np.ndarray:
    """Generate a crisp binary QR code image with a white quiet zone using OpenCV."""
    encoder = cv2.QRCodeEncoder_create()  # type: ignore[attr-defined]
    matrix = encoder.encode(payload)
    scaled = cv2.resize(matrix, (pixel_size, pixel_size), interpolation=cv2.INTER_NEAREST)
    pad = max(12, pixel_size // 10)
    bordered: np.ndarray = cv2.copyMakeBorder(
        scaled, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255
    )
    return bordered


def detect_sheet_qr_payload(image_bgr: np.ndarray) -> SheetQRPayload | None:
    """Detect and decode an OMRKit v2/v3 QR code from an image (any orientation)."""
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
            parsed = parse_sheet_qr_details(text)
            if parsed is not None:
                return parsed

        # Fallback: decodeMulti handles sheets where corner markers confuse single-QR finder
        ok, decoded_list, _, _ = detector.detectAndDecodeMulti(img)
        if ok and decoded_list:
            for item in decoded_list:
                parsed = parse_sheet_qr_details(item)
                if parsed is not None:
                    return parsed

    # Focused high-contrast upscaled pass on small crops (e.g., rectified QR badge)
    if max(h, w) <= 700:
        up = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        _, otsu = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for img in (up, otsu):
            text, _, _ = detector.detectAndDecode(img)
            if text:
                parsed = parse_sheet_qr_details(text)
                if parsed is not None:
                    return parsed

    return None


def detect_sheet_qr(image_bgr: np.ndarray) -> str | None:
    """Detect and decode an OMRKit template ID QR code from an image (any orientation)."""
    payload = detect_sheet_qr_payload(image_bgr)
    return payload.preset_id if payload is not None else None
