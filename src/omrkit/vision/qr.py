"""Embedded QR code encoding and automatic template + student metadata discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote

import cv2
import numpy as np

from omrkit.vision.preprocess import ensure_grayscale

QR_PREFIX = "OMRKIT:v2:"
QR_V3_PREFIX = "OMRKIT:v3:"
_MAX_QR_V3_BYTES = 104


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


def _escape_qr_value(raw: str) -> str:
    """Escape only structural delimiters while preserving raw UTF-8 bytes for compact QR density."""
    cleaned = raw.replace("\r", " ").replace("\n", " ").strip()
    return cleaned.replace("%", "%25").replace("|", "%7C").replace("=", "%3D")


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate a string cleanly on character boundaries so its UTF-8 encoding fits max_bytes."""
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    out_chars: list[str] = []
    used = 0
    for ch in text:
        ch_len = len(ch.encode("utf-8"))
        if used + ch_len > max_bytes:
            break
        out_chars.append(ch)
        used += ch_len
    return "".join(out_chars).rstrip()


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
    and compact raw-UTF-8 ``OMRKIT:v3:<preset_id>|sid=...|b=...|c=...|n=...`` bounded to keep
    200 DPI printed QR modules reliably scannable across Turkish/CJK/Cyrillic scripts.
    """
    pid = preset_id.strip()
    has_any = any(
        val and val.strip() for val in (student_id, student_name, classroom, booklet, email)
    )
    if not has_any:
        return f"{QR_PREFIX}{pid}"

    header = f"{QR_V3_PREFIX}{pid}"
    budget = max(24, _MAX_QR_V3_BYTES - len(header.encode("utf-8")))
    parts: list[str] = []

    def _try_append(key: str, raw_val: str | None, max_field_bytes: int, allow_trunc: bool) -> None:
        nonlocal budget
        if not raw_val or not raw_val.strip():
            return
        escaped = _escape_qr_value(raw_val)
        prefix = f"|{key}="
        avail = min(max_field_bytes, budget - len(prefix))
        if avail <= 0:
            return
        if len(escaped.encode("utf-8")) > avail:
            if not allow_trunc:
                return
            escaped = _truncate_utf8(escaped, avail)
            # Avoid clipping in the middle of a %XX escape sequence
            if len(escaped) >= 1 and escaped[-1] == "%":
                escaped = escaped[:-1]
            elif len(escaped) >= 2 and escaped[-2] == "%":
                escaped = escaped[:-2]
        if not escaped:
            return
        segment = f"{prefix}{escaped}"
        parts.append(segment)
        budget -= len(segment.encode("utf-8"))

    # Priority order: ID -> Booklet -> Classroom -> Name -> Email (only if full email fits)
    _try_append("sid", student_id, 24, allow_trunc=True)
    _try_append("b", booklet.upper() if booklet else None, 6, allow_trunc=True)
    _try_append("c", classroom, 16, allow_trunc=True)
    _try_append("n", student_name, 42, allow_trunc=True)
    _try_append("e", email, 36, allow_trunc=False)

    if not parts:
        return f"{QR_PREFIX}{pid}"
    return header + "".join(parts)


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
    """Generate a crisp integer-scaled binary QR code image with a 4-module white quiet zone."""
    encoder = cv2.QRCodeEncoder_create()  # type: ignore[attr-defined]
    matrix = encoder.encode(payload)
    mod_count = max(1, int(matrix.shape[0]))
    mod_px = max(4, pixel_size // mod_count)
    scaled = np.repeat(np.repeat(matrix, mod_px, axis=0), mod_px, axis=1)
    pad = mod_px * 4
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
    if max(h, w) <= 800:
        for factor in (2, 3):
            up = cv2.resize(gray, (w * factor, h * factor), interpolation=cv2.INTER_CUBIC)
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
