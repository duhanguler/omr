"""Multi-strategy sheet registration and perspective rectification."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from omrkit.models.template import RegistrationConfig, Template
from omrkit.vision.preprocess import ensure_grayscale, rotate_image


class RegistrationError(RuntimeError):
    """Raised when an optical sheet cannot be aligned to its template."""


@dataclass(slots=True)
class RegistrationResult:
    """Warped canonical sheet image and diagnostic alignment metadata."""

    warped_bgr: np.ndarray
    method: str
    score: float
    rotation_deg: int
    source_corners: list[tuple[float, float]] | None = None


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 2D points consistently as [top-left, top-right, bottom-right, bottom-left].

    Uses centroid polar-angle sorting (clockwise in image Y-down coordinates) rotated
    to start at the top-left corner, guaranteeing 4 distinct vertices even on 45-degree
    diamond-oriented quads where sum/diff heuristics can collapse two corners.
    """
    arr = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    centroid = arr.mean(axis=0)
    angles = np.arctan2(arr[:, 1] - centroid[1], arr[:, 0] - centroid[0])
    # In image coordinates (x right, y down), ascending atan2 from -pi to +pi is clockwise
    cw = arr[np.argsort(angles)]
    tl_idx = int(np.argmin(cw[:, 0] + cw[:, 1]))
    return np.roll(cw, -tl_idx, axis=0).astype(np.float32)


def _default_target_corners(template: Template) -> np.ndarray:
    if template.registration.target_corners is not None:
        return np.asarray(template.registration.target_corners, dtype=np.float32)
    w = float(template.page_width - 1)
    h = float(template.page_height - 1)
    return np.asarray([[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]], dtype=np.float32)


def _infer_rotation_from_top_edge(tl: np.ndarray, tr: np.ndarray) -> int:
    """Infer nearest 90-degree clockwise rotation applied to bring TL->TR horizontal."""
    dx = float(tr[0] - tl[0])
    dy = float(tr[1] - tl[1])
    angle = math.degrees(math.atan2(dy, dx))
    # Snap to nearest quadrant: 0=upright, 90=rotated CW (needs 270), etc.
    snapped = (round(-angle / 90.0) * 90) % 360
    return int(snapped)


def _warp_from_corners(
    image_bgr: np.ndarray,
    src_corners: np.ndarray,
    dst_corners: np.ndarray,
    page_width: int,
    page_height: int,
) -> np.ndarray:
    matrix = cv2.getPerspectiveTransform(
        src_corners.astype(np.float32),
        dst_corners.astype(np.float32),
    )
    return cv2.warpPerspective(
        image_bgr,
        matrix,
        (page_width, page_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _get_aruco_dictionary(dict_name: str) -> cv2.aruco.Dictionary:
    if not hasattr(cv2.aruco, dict_name):
        raise RegistrationError(f"Unknown ArUco dictionary '{dict_name}'.")
    dict_id = getattr(cv2.aruco, dict_name)
    return cv2.aruco.getPredefinedDictionary(dict_id)


def _register_aruco(image_bgr: np.ndarray, template: Template) -> RegistrationResult:
    cfg = template.registration
    aruco_dict = _get_aruco_dictionary(cfg.aruco_dict)
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    gray = ensure_grayscale(image_bgr)
    required_ids = list(cfg.aruco_ids)

    def _detect_markers(img: np.ndarray, inv_scale: float = 1.0) -> dict[int, np.ndarray]:
        corners, ids, _ = detector.detectMarkers(img)
        found: dict[int, np.ndarray] = {}
        best_area: dict[int, float] = {}
        if ids is None:
            return found
        for marker_corners, marker_id_val in zip(corners, np.asarray(ids).ravel(), strict=False):
            mid = int(marker_id_val)
            if mid in required_ids:
                pts4 = np.asarray(marker_corners, dtype=np.float32).reshape(4, 2) * inv_scale
                area = abs(float(cv2.contourArea(pts4)))
                if area < 100.0:
                    continue
                if mid not in found or area > best_area[mid]:
                    found[mid] = pts4
                    best_area[mid] = area
        return found

    # Attempt 1: Native resolution grayscale
    found = _detect_markers(gray, 1.0)

    # Attempt 2: CLAHE contrast-enhanced grayscale (helps shadowed phone photos)
    if len(found) < 4:
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        found_clahe = _detect_markers(clahe.apply(gray), 1.0)
        if len(found_clahe) > len(found):
            found = found_clahe

    # Attempt 3: Downscaled pass for very high-res noisy camera captures
    if len(found) < 4 and max(gray.shape[:2]) > 2000:
        scale = 1600.0 / float(max(gray.shape[:2]))
        small = cv2.resize(
            gray,
            (int(gray.shape[1] * scale), int(gray.shape[0] * scale)),
            interpolation=cv2.INTER_AREA,
        )
        found_small = _detect_markers(small, 1.0 / scale)
        if len(found_small) > len(found):
            found = found_small

    dst_pts = _default_target_corners(template)

    if len(found) == 4:
        src_pts = np.asarray([found[mid].mean(axis=0) for mid in required_ids], dtype=np.float32)
        rotation = _infer_rotation_from_top_edge(src_pts[0], src_pts[1])
        warped = _warp_from_corners(
            image_bgr, src_pts, dst_pts, template.page_width, template.page_height
        )
        return RegistrationResult(
            warped_bgr=warped,
            method="aruco",
            score=1.0,
            rotation_deg=rotation,
            source_corners=[(float(p[0]), float(p[1])) for p in src_pts],
        )

    # 3-of-4 Occluded ArUco Recovery: use all 12 subpixel inner corners (3 markers x 4 corners)
    # to recover the full 2D projective homography even when a thumb/staple covers 1 corner.
    if len(found) == 3:
        present_indices = [idx for idx, mid in enumerate(required_ids) if mid in found]
        src_sides = [
            float(
                np.mean(
                    [
                        np.linalg.norm(
                            found[required_ids[idx]][(k + 1) % 4] - found[required_ids[idx]][k]
                        )
                        for k in range(4)
                    ]
                )
            )
            for idx in present_indices
        ]
        if max(src_sides) <= 0.0 or (min(src_sides) / max(src_sides)) < 0.45:
            missing = [mid for mid in required_ids if mid not in found]
            raise RegistrationError(
                f"ArUco 3-corner recovery rejected: inconsistent marker scales (missing IDs: {missing})."
            )

        src_centers_3 = np.asarray(
            [found[required_ids[idx]].mean(axis=0) for idx in present_indices], dtype=np.float32
        )
        dst_centers_3 = np.asarray([dst_pts[idx] for idx in present_indices], dtype=np.float32)
        affine_mat = cv2.getAffineTransform(src_centers_3, dst_centers_3)

        # Estimate the canonical black-square half-width in target pixels from the 3 visible markers
        half_extents: list[float] = []
        for idx in present_indices:
            pts4 = found[required_ids[idx]]
            ones = np.ones((4, 1), dtype=np.float32)
            mapped = (np.hstack([pts4, ones]) @ affine_mat.T).astype(np.float32)
            dx_span = (
                float(np.linalg.norm(mapped[1] - mapped[0]) + np.linalg.norm(mapped[2] - mapped[3]))
                * 0.25
            )
            dy_span = (
                float(np.linalg.norm(mapped[3] - mapped[0]) + np.linalg.norm(mapped[2] - mapped[1]))
                * 0.25
            )
            half_extents.extend([dx_span, dy_span])
        half_side = float(np.median(half_extents)) if half_extents else 0.0
        if half_side < 4.0 or (min(half_extents) / max(half_extents)) < 0.40:
            missing = [mid for mid in required_ids if mid not in found]
            raise RegistrationError(
                f"ArUco 3-corner recovery rejected: degenerate marker geometry (missing IDs: {missing})."
            )

        src_12_list: list[np.ndarray] = []
        dst_12_list: list[np.ndarray] = []
        for idx in present_indices:
            cx, cy = float(dst_pts[idx][0]), float(dst_pts[idx][1])
            src_12_list.append(found[required_ids[idx]])
            dst_12_list.append(
                np.asarray(
                    [
                        [cx - half_side, cy - half_side],
                        [cx + half_side, cy - half_side],
                        [cx + half_side, cy + half_side],
                        [cx - half_side, cy + half_side],
                    ],
                    dtype=np.float32,
                )
            )
        src_12 = np.vstack(src_12_list)
        dst_12 = np.vstack(dst_12_list)

        homography, _ = cv2.findHomography(src_12, dst_12, 0)
        if homography is not None and np.isfinite(homography).all():
            det = float(np.linalg.det(homography))
            projected = cv2.perspectiveTransform(src_12.reshape(-1, 1, 2), homography).reshape(
                -1, 2
            )
            errs = np.linalg.norm(projected - dst_12, axis=1)
            med_err = float(np.median(errs))
            max_err = float(np.max(errs))
            if (
                abs(det) > 1e-12
                and med_err <= max(10.0, half_side * 0.35)
                and max_err <= max(24.0, half_side * 0.85)
            ):
                warped = cv2.warpPerspective(
                    image_bgr,
                    homography,
                    (template.page_width, template.page_height),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(255, 255, 255),
                )
                # Infer top-edge direction from first visible marker's own TL->TR edge
                m0 = found[required_ids[present_indices[0]]]
                rotation = _infer_rotation_from_top_edge(m0[0], m0[1])
                return RegistrationResult(
                    warped_bgr=warped,
                    method="aruco_3pt",
                    score=0.92,
                    rotation_deg=rotation,
                    source_corners=[(float(p[0]), float(p[1])) for p in src_centers_3],
                )

    missing = [mid for mid in required_ids if mid not in found]
    raise RegistrationError(
        f"ArUco registration failed: detected {len(found)}/4 markers (missing IDs: {missing})."
    )


def _prepare_marker_image(
    marker_gray: np.ndarray, target_w: int, erode_subtract: bool
) -> np.ndarray:
    h, w = marker_gray.shape[:2]
    target_h = max(8, round(h * (target_w / float(w))))
    resized = cv2.resize(marker_gray, (max(8, target_w), target_h), interpolation=cv2.INTER_AREA)
    blurred = cv2.GaussianBlur(resized, (5, 5), 0)
    normed = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
    if erode_subtract:
        kernel = np.ones((5, 5), dtype=np.uint8)
        normed = cv2.subtract(normed, cv2.erode(normed, kernel, iterations=5))
    return normed


def _match_four_markers(
    image_bgr: np.ndarray,
    marker_gray: np.ndarray,
    cfg: RegistrationConfig,
) -> tuple[np.ndarray, float] | None:
    gray = ensure_grayscale(image_bgr)
    orig_h, orig_w = gray.shape[:2]
    work_w = 800
    scale_to_work = work_w / float(orig_w)
    work_h = max(64, round(orig_h * scale_to_work))
    work = cv2.resize(gray, (work_w, work_h), interpolation=cv2.INTER_AREA)

    if cfg.erode_subtract:
        kernel = np.ones((5, 5), dtype=np.uint8)
        work_proc = cv2.subtract(work, cv2.erode(work, kernel, iterations=5))
    else:
        work_proc = work
    work_proc = cv2.normalize(work_proc, None, 0, 255, cv2.NORM_MINMAX)

    base_marker_w = max(12, round(work_w / cfg.sheet_to_marker_width_ratio))
    base_marker = _prepare_marker_image(marker_gray, base_marker_w, cfg.erode_subtract)

    mid_x = round(work_w * cfg.split_ratio_x)
    mid_y = round(work_h * cfg.split_ratio_y)
    quads = [
        (0, 0, work_proc[0:mid_y, 0:mid_x]),  # TL
        (mid_x, 0, work_proc[0:mid_y, mid_x:work_w]),  # TR
        (mid_x, mid_y, work_proc[mid_y:work_h, mid_x:work_w]),  # BR
        (0, mid_y, work_proc[mid_y:work_h, 0:mid_x]),  # BL
    ]

    min_s, max_s = cfg.scale_range
    scales = np.linspace(max_s, min_s, cfg.scale_steps)
    best_scale: float | None = None
    best_global_score = -1.0

    mh, mw = base_marker.shape[:2]
    for s in scales:
        tw = max(8, round(mw * float(s)))
        th = max(8, round(mh * float(s)))
        if tw >= min(mid_x, work_w - mid_x) or th >= min(mid_y, work_h - mid_y):
            continue
        scaled = cv2.resize(base_marker, (tw, th), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(work_proc, scaled, cv2.TM_CCOEFF_NORMED)
        score = float(np.max(res))
        if score > best_global_score:
            best_global_score = score
            best_scale = float(s)

    if best_scale is None or best_global_score < cfg.min_match_score:
        return None

    tw = max(8, round(mw * best_scale))
    th = max(8, round(mh * best_scale))
    optimal_marker = cv2.resize(base_marker, (tw, th), interpolation=cv2.INTER_AREA)

    centers: list[tuple[float, float]] = []
    quad_scores: list[float] = []
    for ox, oy, quad in quads:
        if quad.shape[0] <= th or quad.shape[1] <= tw:
            return None
        res = cv2.matchTemplate(quad, optimal_marker, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        score_val = float(max_val)
        if (
            score_val < cfg.min_match_score
            or abs(best_global_score - score_val) > cfg.max_match_variation
        ):
            return None
        cx_work = ox + max_loc[0] + tw / 2.0
        cy_work = oy + max_loc[1] + th / 2.0
        centers.append((cx_work / scale_to_work, cy_work / scale_to_work))
        quad_scores.append(score_val)

    # Validate geometry: markers must form a non-degenerate convex quad with sensible area
    pts = np.asarray(centers, dtype=np.float32)
    area = float(cv2.contourArea(pts))
    if area < 0.05 * orig_w * orig_h:
        return None

    return pts, float(np.mean(quad_scores))


def _template_structure_score(warped_bgr: np.ndarray, template: Template) -> float:
    """Measure ratio of printed edge density inside template blocks vs outside margins."""
    scale = 0.25
    mw = max(32, round(template.page_width * scale))
    mh = max(32, round(template.page_height * scale))
    mask = np.zeros((mh, mw), dtype=bool)
    for blk in template.blocks:
        xs: list[float] = []
        ys: list[float] = []
        for _, coords in blk.iter_field_bubbles():
            for c in coords:
                xs.append(c.cx)
                ys.append(c.cy)
        if not xs:
            continue
        r = blk.bubble_radius
        x1 = max(0, round((min(xs) - r) * scale))
        x2 = min(mw, round((max(xs) + r) * scale))
        y1 = max(0, round((min(ys) - r) * scale))
        y2 = min(mh, round((max(ys) + r) * scale))
        mask[y1:y2, x1:x2] = True

    if not mask.any() or mask.all():
        return 1.0
    gray = cv2.resize(ensure_grayscale(warped_bgr), (mw, mh), interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(gray, 40, 120) > 0
    in_density = float(np.mean(edges[mask]))
    out_density = float(np.mean(edges[~mask]))
    return in_density / (out_density + 0.005)


def _register_markers(image_bgr: np.ndarray, template: Template) -> RegistrationResult:
    cfg = template.registration
    if not cfg.marker_path:
        raise RegistrationError("Marker registration requires 'registration.marker_path'.")

    marker_path = Path(cfg.marker_path)
    if not marker_path.exists():
        raise RegistrationError(f"Marker image not found: '{marker_path}'")

    marker_gray = cv2.imread(str(marker_path), cv2.IMREAD_GRAYSCALE)
    if marker_gray is None:
        raise RegistrationError(f"Could not decode marker image: '{marker_path}'")

    candidate_rotations = [0, 90, 270, 180] if cfg.auto_rotate else [0]
    expected_aspect = template.page_width / float(template.page_height)
    dst_pts = _default_target_corners(template)
    best_match: tuple[int, np.ndarray, np.ndarray, float, float] | None = None

    for deg in candidate_rotations:
        rotated = rotate_image(image_bgr, deg)
        result = _match_four_markers(rotated, marker_gray, cfg)
        if result is None:
            continue
        pts, match_score = result
        warped = _warp_from_corners(
            rotated, pts, dst_pts, template.page_width, template.page_height
        )

        quad_w = 0.5 * (
            float(np.linalg.norm(pts[1] - pts[0])) + float(np.linalg.norm(pts[2] - pts[3]))
        )
        quad_h = 0.5 * (
            float(np.linalg.norm(pts[3] - pts[0])) + float(np.linalg.norm(pts[2] - pts[1]))
        )
        quad_aspect = quad_w / max(quad_h, 1.0)
        aspect_err = abs(math.log(max(quad_aspect, 1e-3) / expected_aspect))
        structure_ratio = _template_structure_score(warped, template)

        combined_rank = match_score + 0.45 * min(structure_ratio, 3.0) - 1.2 * aspect_err
        if best_match is None or combined_rank > best_match[4]:
            best_match = (deg, warped, pts, match_score, combined_rank)

    if best_match is None:
        raise RegistrationError(
            "Marker registration failed: could not locate all 4 corner markers."
        )

    deg, warped, src_pts, score, _ = best_match
    return RegistrationResult(
        warped_bgr=warped,
        method="markers",
        score=round(score, 4),
        rotation_deg=deg,
        source_corners=[(float(p[0]), float(p[1])) for p in src_pts],
    )


def _check_quad_angles(pts: np.ndarray, max_cosine: float = 0.38) -> bool:
    for i in range(4):
        p0 = pts[i]
        p1 = pts[(i - 1) % 4]
        p2 = pts[(i + 1) % 4]
        v1 = p1 - p0
        v2 = p2 - p0
        denom = float(np.linalg.norm(v1) * np.linalg.norm(v2)) + 1e-9
        cos_val = abs(float(np.dot(v1, v2)) / denom)
        if cos_val >= max_cosine:
            return False
    return True


def _register_page_quad(image_bgr: np.ndarray, template: Template) -> RegistrationResult:
    cfg = template.registration
    gray = ensure_grayscale(image_bgr)
    h, w = gray.shape[:2]
    min_area = cfg.min_area_ratio * float(h * w)

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    normed = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
    _, trunc = cv2.threshold(normed, 200, 255, cv2.THRESH_TRUNC)
    normed = cv2.normalize(trunc, None, 0, 255, cv2.NORM_MINMAX)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, cfg.morph_kernel)
    closed = cv2.morphologyEx(normed, cv2.MORPH_CLOSE, kernel)
    edges = cv2.Canny(closed, 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    hulls = [cv2.convexHull(c) for c in contours]
    hulls = sorted(hulls, key=cv2.contourArea, reverse=True)[:8]

    for hull in hulls:
        area = float(cv2.contourArea(hull))
        if area < min_area:
            continue
        peri = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.025 * peri, True)
        if len(approx) == 4:
            pts = order_quad_points(approx.reshape(4, 2))
            if _check_quad_angles(pts):
                dst_pts = _default_target_corners(template)
                warped = _warp_from_corners(
                    image_bgr, pts, dst_pts, template.page_width, template.page_height
                )
                coverage = min(1.0, area / float(h * w))
                return RegistrationResult(
                    warped_bgr=warped,
                    method="page_quad",
                    score=round(max(0.5, coverage), 4),
                    rotation_deg=0,
                    source_corners=[(float(p[0]), float(p[1])) for p in pts],
                )

    raise RegistrationError("Page boundary quadrilateral not found in image.")


def _register_homography(image_bgr: np.ndarray, template: Template) -> RegistrationResult:
    cfg = template.registration
    if not cfg.reference_path:
        raise RegistrationError("Homography registration requires 'registration.reference_path'.")

    ref_path = Path(cfg.reference_path)
    if not ref_path.exists():
        raise RegistrationError(f"Reference image not found: '{ref_path}'")

    ref_gray = cv2.imread(str(ref_path), cv2.IMREAD_GRAYSCALE)
    if ref_gray is None:
        raise RegistrationError(f"Could not decode reference image: '{ref_path}'")
    ref_gray = cv2.resize(
        ref_gray, (template.page_width, template.page_height), interpolation=cv2.INTER_AREA
    )

    src_gray = cv2.normalize(ensure_grayscale(image_bgr), None, 0, 255, cv2.NORM_MINMAX)
    ref_norm = cv2.normalize(ref_gray, None, 0, 255, cv2.NORM_MINMAX)

    orb = cv2.ORB_create(cfg.max_features)  # type: ignore[attr-defined]
    kp_src, des_src = orb.detectAndCompute(src_gray, None)
    kp_ref, des_ref = orb.detectAndCompute(ref_norm, None)

    if des_src is None or des_ref is None or len(kp_src) < 8 or len(kp_ref) < 8:
        raise RegistrationError("Insufficient ORB keypoints for homography alignment.")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(matcher.match(des_src, des_ref), key=lambda m: m.distance)
    keep = max(8, int(len(matches) * cfg.good_match_ratio))
    good_matches = matches[:keep]

    if len(good_matches) < 8:
        raise RegistrationError(f"Only {len(good_matches)} feature matches found (need >= 8).")

    pts_src = np.asarray([kp_src[m.queryIdx].pt for m in good_matches], dtype=np.float32).reshape(
        -1, 1, 2
    )
    pts_ref = np.asarray([kp_ref[m.trainIdx].pt for m in good_matches], dtype=np.float32).reshape(
        -1, 1, 2
    )

    matrix, mask = cv2.findHomography(pts_src, pts_ref, cv2.RANSAC, 5.0)
    if matrix is None:
        raise RegistrationError("RANSAC homography estimation failed.")

    inlier_ratio = (
        float(np.mean(np.asarray(mask, dtype=np.float32)))
        if mask is not None and mask.size > 0
        else 0.5
    )
    warped = cv2.warpPerspective(
        image_bgr,
        matrix,
        (template.page_width, template.page_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return RegistrationResult(
        warped_bgr=warped,
        method="homography",
        score=round(inlier_ratio, 4),
        rotation_deg=0,
    )


def register_sheet(image_bgr: np.ndarray, template: Template) -> RegistrationResult:
    """Align and perspective-warp an input sheet image to canonical template coordinates."""
    mode = template.registration.mode
    if mode == "aruco":
        return _register_aruco(image_bgr, template)
    if mode == "markers":
        return _register_markers(image_bgr, template)
    if mode == "page_quad":
        return _register_page_quad(image_bgr, template)
    if mode == "homography":
        return _register_homography(image_bgr, template)

    resized = cv2.resize(
        image_bgr,
        (template.page_width, template.page_height),
        interpolation=cv2.INTER_AREA,
    )
    return RegistrationResult(
        warped_bgr=resized,
        method="none",
        score=1.0,
        rotation_deg=0,
    )
