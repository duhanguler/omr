"""Automatic blank-form bubble grid finder for zero-friction custom template bootstrapping."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import cv2
import numpy as np

from omrkit.models.template import (
    DetectionConfig,
    FieldBlock,
    RegistrationConfig,
    Template,
)
from omrkit.vision.preprocess import ensure_grayscale, normalize_illumination


@dataclass(slots=True)
class DetectedCircle:
    """A candidate optical bubble contour found on a blank form."""

    cx: float
    cy: float
    radius: float


def _find_candidate_bubbles(image_bgr: np.ndarray) -> list[DetectedCircle]:
    """Detect printed hollow circular bubbles via adaptive threshold and circularity filtering."""
    gray = normalize_illumination(ensure_grayscale(image_bgr))
    h, w = gray.shape[:2]
    min_dim = min(h, w)

    # Reasonable bubble radius bounds relative to page width (e.g., 0.5% to 2.8% of min_dim)
    min_r = max(5.0, min_dim * 0.0065)
    max_r = max(24.0, min_dim * 0.026)

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    block_size = max(15, (round(min_dim * 0.025) | 1))
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        8,
    )
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_k)

    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    raw: list[DetectedCircle] = []

    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < math.pi * (min_r * 0.72) ** 2 or area > math.pi * (max_r * 1.25) ** 2:
            continue
        peri = float(cv2.arcLength(cnt, True))
        if peri <= 1e-6:
            continue
        circularity = (4.0 * math.pi * area) / (peri * peri)
        if circularity < 0.58:
            continue

        _x, _y, bw, bh = cv2.boundingRect(cnt)
        aspect = bw / max(float(bh), 1.0)
        if aspect < 0.72 or aspect > 1.38:
            continue

        (cx, cy), radius = cv2.minEnclosingCircle(cnt)
        if min_r <= radius <= max_r:
            raw.append(DetectedCircle(cx=float(cx), cy=float(cy), radius=float(radius)))

    if not raw:
        return []

    # Filter to dominant bubble radius cluster (eliminates tiny dots or huge logos/markers)
    radii = np.asarray([c.radius for c in raw], dtype=np.float32)
    median_r = float(np.median(radii))
    consistent = [c for c in raw if 0.72 * median_r <= c.radius <= 1.32 * median_r]

    # Non-maximum deduplication (inner/outer contour of the same circle outline)
    consistent.sort(key=lambda c: c.radius, reverse=True)
    deduped: list[DetectedCircle] = []
    min_dist_sq = (median_r * 1.15) ** 2
    for cand in consistent:
        if all(
            (cand.cx - kept.cx) ** 2 + (cand.cy - kept.cy) ** 2 > min_dist_sq for kept in deduped
        ):
            deduped.append(cand)

    return deduped


def _cluster_rows(circles: list[DetectedCircle], y_tol: float) -> list[list[DetectedCircle]]:
    """Group circles sharing roughly the same Y coordinate into horizontal strips."""
    sorted_c = sorted(circles, key=lambda c: c.cy)
    rows: list[list[DetectedCircle]] = []
    for c in sorted_c:
        if not rows or abs(c.cy - float(np.mean([p.cy for p in rows[-1]]))) > y_tol:
            rows.append([c])
        else:
            rows[-1].append(c)
    for row in rows:
        row.sort(key=lambda c: c.cx)
    return rows


def _split_row_segments(row: list[DetectedCircle], max_gap: float) -> list[list[DetectedCircle]]:
    """Split a horizontal row of bubbles into contiguous option groups separated by large X gaps."""
    if not row:
        return []
    segments: list[list[DetectedCircle]] = [[row[0]]]
    for c in row[1:]:
        if c.cx - segments[-1][-1].cx <= max_gap:
            segments[-1].append(c)
        else:
            segments.append([c])
    return [seg for seg in segments if len(seg) >= 3]


def _estimate_skew_angle(circles: list[DetectedCircle], median_r: float) -> float:
    """Estimate dominant horizontal grid skew angle in degrees within [-12, +12]."""
    angles: list[float] = []
    max_dx = median_r * 7.5
    min_dx = median_r * 1.6
    max_dy = median_r * 2.5

    for c in circles:
        best_dist = float("inf")
        best_angle: float | None = None
        for other in circles:
            dx = other.cx - c.cx
            if dx < min_dx or dx > max_dx:
                continue
            dy = other.cy - c.cy
            if abs(dy) > max_dy:
                continue
            dist = dx * dx + dy * dy
            if dist < best_dist:
                ang = math.degrees(math.atan2(dy, dx))
                if abs(ang) <= 12.0:
                    best_dist = dist
                    best_angle = ang
        if best_angle is not None:
            angles.append(best_angle)

    if len(angles) < 8:
        return 0.0
    return float(np.median(angles))


def detect_layout_from_blank_with_image(
    image_bgr: np.ndarray,
    template_name: str = "auto_detected_template",
) -> tuple[Template, int, np.ndarray]:
    """Infer OMRKit FieldBlocks from a blank form and return (Template, bubble_count, aligned_bgr).

    Automatically detects and corrects minor page tilt (up to +/-12 degrees) before clustering,
    returning the aligned image that matches the emitted template coordinates pixel-for-pixel.
    """
    h, w = image_bgr.shape[:2]
    circles = _find_candidate_bubbles(image_bgr)
    if len(circles) < 4:
        raise ValueError(
            f"Could not detect enough circular bubbles ({len(circles)} found). "
            "Upload a clean blank sheet image or draw blocks manually."
        )

    aligned_bgr = image_bgr
    applied_skew_deg = 0.0
    median_r = float(np.median([c.radius for c in circles]))
    skew_deg = _estimate_skew_angle(circles, median_r)
    if abs(skew_deg) >= 0.4:
        rot_mat = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), skew_deg, 1.0)
        deskewed = cv2.warpAffine(
            image_bgr,
            rot_mat,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
        deskewed_circles = _find_candidate_bubbles(deskewed)
        if len(deskewed_circles) >= max(4, int(len(circles) * 0.75)):
            circles = deskewed_circles
            median_r = float(np.median([c.radius for c in circles]))
            aligned_bgr = deskewed
            applied_skew_deg = round(skew_deg, 2)

    rows = _cluster_rows(circles, y_tol=median_r * 0.9)

    # Estimate typical intra-group spacing from nearest horizontal neighbor distances
    horiz_diffs: list[float] = []
    for row in rows:
        for a, b in itertools.pairwise(row):
            dx = b.cx - a.cx
            if median_r * 1.6 <= dx <= median_r * 7.5:
                horiz_diffs.append(dx)
    base_gap = float(np.median(horiz_diffs)) if horiz_diffs else median_r * 3.0
    max_intra_gap = base_gap * 1.65

    # Extract horizontal bubble segments across all rows
    all_segments: list[tuple[float, float, int, list[DetectedCircle]]] = []
    for row in rows:
        for seg in _split_row_segments(row, max_gap=max_intra_gap):
            x_start = seg[0].cx
            y_mean = float(np.mean([p.cy for p in seg]))
            all_segments.append((x_start, y_mean, len(seg), seg))

    # Stack aligned segments top-to-bottom within each horizontal column band
    band_w = max(12.0, median_r * 3.0)
    all_segments.sort(key=lambda item: (round(item[0] / band_w), item[1]))
    used = [False] * len(all_segments)
    raw_groups: list[list[list[DetectedCircle]]] = []

    for i, (x0, y0, n_opts, seg0) in enumerate(all_segments):
        if used[i]:
            continue
        used[i] = True
        stack: list[list[DetectedCircle]] = [seg0]
        last_y = y0

        candidates = sorted(
            (
                (all_segments[j][1], j)
                for j in range(len(all_segments))
                if not used[j]
                and all_segments[j][2] == n_opts
                and abs(all_segments[j][0] - x0) <= median_r * 1.3
                and all_segments[j][1] > last_y
            ),
            key=lambda pair: pair[0],
        )
        max_step_y = max(median_r * 8.0, base_gap * 3.1)
        for cand_y, j in candidates:
            if cand_y - last_y <= max_step_y:
                used[j] = True
                stack.append(all_segments[j][3])
                last_y = cand_y

        if len(stack) >= 2:
            raw_groups.append(stack)

    # Sort detected blocks left-to-right, then top-to-bottom
    raw_groups.sort(key=lambda g: (round(g[0][0].cx / 80.0), g[0][0].cy))

    blocks: list[FieldBlock] = []
    q_counter = 1
    id_counter = 1

    for stack in raw_groups:
        n_cols = len(stack[0])
        xs_start = [row[0].cx for row in stack]
        ys_rows = [float(np.mean([p.cy for p in row])) for row in stack]

        origin_x = round(float(np.median(xs_start)), 1)
        origin_y = round(ys_rows[0], 1)

        col_gaps = [
            (row[-1].cx - row[0].cx) / float(max(1, n_cols - 1)) for row in stack if n_cols > 1
        ]
        raw_row_gaps = [
            ys_rows[k + 1] - ys_rows[k]
            for k in range(len(ys_rows) - 1)
            if (ys_rows[k + 1] - ys_rows[k]) >= median_r * 1.5
        ]
        # Use lower-half median of plausible row gaps to ignore occasional skipped rows
        if raw_row_gaps:
            min_gap = float(np.min(raw_row_gaps))
            unit_gaps = [g for g in raw_row_gaps if g <= min_gap * 1.45]
            dy_val = float(np.median(unit_gaps)) if unit_gaps else base_gap
        else:
            dy_val = base_gap
        # Reconstruct exact row count spanning first to last detected row
        span_y = max(0.0, ys_rows[-1] - ys_rows[0])
        n_rows = max(len(stack), round(span_y / max(dy_val, median_r * 1.5)) + 1)

        dx = round(float(np.median(col_gaps)) if col_gaps else base_gap, 2)
        dy = round(max(median_r * 1.5, span_y / float(max(1, n_rows - 1))), 2)
        radius = round(median_r, 1)

        # Heuristic: 10-row grid is almost always a vertical 0-9 digit ID block
        if n_rows == 10 and n_cols >= 4:
            gid = f"ID_GRID_{id_counter}"
            prefix_letter = chr(ord("a") + (id_counter - 1) % 26)
            id_counter += 1
            blocks.append(
                FieldBlock(
                    name=gid,
                    field_type="grid_digits",
                    direction="vertical",
                    origin=(origin_x, origin_y),
                    origin_mode="center",
                    bubble_radius=radius,
                    bubbles_gap=dy,
                    labels_gap=dx,
                    options=[str(d) for d in range(10)],
                    labels=[f"id{prefix_letter}_1..{n_cols}"],
                    group_as=gid,
                    validator="digits",
                )
            )
        else:
            opt_labels = [
                chr(ord("A") + idx) if idx < 26 else f"O{idx + 1}" for idx in range(n_cols)
            ]
            end_q = q_counter + n_rows - 1
            blocks.append(
                FieldBlock(
                    name=f"MCQ_BLOCK_{len(blocks) + 1}",
                    field_type="mcq",
                    direction="horizontal",
                    origin=(origin_x, origin_y),
                    origin_mode="center",
                    bubble_radius=radius,
                    bubbles_gap=dx,
                    labels_gap=dy,
                    options=opt_labels,
                    labels=[f"q{q_counter}..{end_q}"],
                )
            )
            q_counter = end_q + 1

    if not blocks:
        raise ValueError(
            f"Detected {len(circles)} bubbles but could not cluster them into regular grids."
        )

    template = Template(
        version="2.0",
        name=template_name,
        description=f"Auto-detected layout ({len(blocks)} blocks, {len(circles)} candidate bubbles)",
        page_width=w,
        page_height=h,
        registration=RegistrationConfig(mode="none"),
        detection=DetectionConfig(),
        blocks=blocks,
        metadata={
            "auto_detected_bubbles": len(circles),
            "deskew_deg": applied_skew_deg,
        },
    )
    return template, len(circles), aligned_bgr


def detect_layout_from_blank(
    image_bgr: np.ndarray,
    template_name: str = "auto_detected_template",
) -> tuple[Template, int]:
    """Automatically infer OMRKit FieldBlocks from a blank optical form image."""
    template, count, _ = detect_layout_from_blank_with_image(image_bgr, template_name=template_name)
    return template, count
