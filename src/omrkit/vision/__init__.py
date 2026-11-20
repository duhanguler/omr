"""Computer vision pipeline for OMRKit."""

from omrkit.vision.detector import HybridBubbleDetector
from omrkit.vision.preprocess import ensure_grayscale, normalize_illumination, rotate_image
from omrkit.vision.registration import RegistrationError, RegistrationResult, register_sheet
from omrkit.vision.visualizer import render_annotated_sheet

__all__ = [
    "HybridBubbleDetector",
    "RegistrationError",
    "RegistrationResult",
    "ensure_grayscale",
    "normalize_illumination",
    "register_sheet",
    "render_annotated_sheet",
    "rotate_image",
]
