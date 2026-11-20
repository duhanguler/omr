"""Image preprocessing utilities for shadow-invariant optical mark reading."""

from __future__ import annotations

import cv2
import numpy as np


def ensure_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR/BGRA or single-channel image to 8-bit grayscale."""
    if image.ndim == 2:
        return image.astype(np.uint8, copy=False)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def normalize_illumination(gray: np.ndarray, blur_ratio: float = 0.045) -> np.ndarray:
    """Remove uneven lighting and camera shadows via smooth background division.

    Estimates the slowly varying paper illumination field on a downscaled copy for
    speed, then divides pixel intensity by that field so marks retain high contrast
    even under harsh shadows or warm indoor lighting.
    """
    h, w = gray.shape[:2]
    scale = 4 if min(h, w) >= 600 else 2
    small_w = max(32, w // scale)
    small_h = max(32, h // scale)
    small = cv2.resize(gray, (small_w, small_h), interpolation=cv2.INTER_AREA)

    # Morphological closing removes dark ink/bubbles from the background estimate
    close_k = max(5, int(min(small_w, small_h) * 0.025) | 1)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
    bg_small = cv2.morphologyEx(small, cv2.MORPH_CLOSE, close_kernel)

    blur_k = max(7, int(min(small_w, small_h) * blur_ratio) | 1)
    bg_small = cv2.GaussianBlur(bg_small, (blur_k, blur_k), 0)
    bg = cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_LINEAR)

    # Divide gray by background illumination to flatten lighting gradients
    ratio = (gray.astype(np.float32) + 1.0) / (bg.astype(np.float32) + 1.0)
    normalized = np.clip(ratio * 245.0, 0.0, 255.0).astype(np.uint8)
    return normalized


def rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    """Rotate an image clockwise by a multiple of 90 degrees."""
    normalized_deg = degrees % 360
    if normalized_deg == 0:
        return image
    if normalized_deg == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if normalized_deg == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if normalized_deg == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"Expected a multiple of 90 degrees, got {degrees}.")
