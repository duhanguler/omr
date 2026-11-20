"""Computer vision pipeline for OMRKit."""

from omrkit.vision.detector import HybridBubbleDetector
from omrkit.vision.grid_finder import DetectedCircle, detect_layout_from_blank
from omrkit.vision.preprocess import ensure_grayscale, normalize_illumination, rotate_image
from omrkit.vision.qr import (
    detect_sheet_qr,
    encode_sheet_qr_payload,
    parse_sheet_qr_payload,
    render_qr_matrix,
)
from omrkit.vision.registration import RegistrationError, RegistrationResult, register_sheet
from omrkit.vision.visualizer import render_annotated_sheet

__all__ = [
    "DetectedCircle",
    "HybridBubbleDetector",
    "RegistrationError",
    "RegistrationResult",
    "detect_layout_from_blank",
    "detect_sheet_qr",
    "encode_sheet_qr_payload",
    "ensure_grayscale",
    "normalize_illumination",
    "parse_sheet_qr_payload",
    "register_sheet",
    "render_annotated_sheet",
    "render_qr_matrix",
    "rotate_image",
]
