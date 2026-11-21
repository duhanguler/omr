"""Shape-aware hybrid bubble detector with calibrated HITL confidence scoring."""

from __future__ import annotations

import math
from functools import lru_cache

import cv2
import numpy as np

from omrkit.models.scan import BubbleReading, FieldReading, FieldStatus, ReviewItem
from omrkit.models.template import BubbleCoord, DetectionConfig, FieldBlock, Template
from omrkit.vision.preprocess import ensure_grayscale, normalize_illumination


@lru_cache(maxsize=64)
def _radial_masks(
    half_size: int,
    radius: float,
    inner_ratio: float,
    ring_inner_ratio: float,
    ring_outer_ratio: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Build cached circular inner-core and local-background-ring boolean masks."""
    size = 2 * half_size + 1
    yy, xx = np.ogrid[:size, :size]
    dist_sq = (xx - half_size) ** 2 + (yy - half_size) ** 2
    inner_r = max(1.5, radius * inner_ratio)
    ring_in = radius * ring_inner_ratio
    ring_out = radius * ring_outer_ratio
    inner_mask = dist_sq <= inner_r**2
    ring_mask = (dist_sq >= ring_in**2) & (dist_sq <= ring_out**2)
    return inner_mask, ring_mask


class HybridBubbleDetector:
    """Evaluates bubble markings using fill ratio, ring contrast, and ink stroke density.

    Handles solid fills, partial fills, pen checkmarks/crosses, erased pencil smudges,
    printed letters inside bubbles, local photocopy drift, and uneven shadows while
    emitting calibrated per-field confidence scores and HITL review flags.
    """

    def __init__(self, config: DetectionConfig | None = None) -> None:
        self.config = config or DetectionConfig()

    @staticmethod
    def _estimate_block_offset(
        proc_gray: np.ndarray,
        block_coords: list[tuple[str, list[BubbleCoord]]],
        radius: float,
        max_shift: int,
    ) -> tuple[float, float]:
        """Estimate local (dx, dy) photocopy/paper drift for a block via ring-edge correlation."""
        if max_shift <= 0 or not block_coords:
            return 0.0, 0.0

        all_c = [c for _, coords in block_coords for c in coords]
        if len(all_c) < 4:
            return 0.0, 0.0

        h, w = proc_gray.shape[:2]
        pad = max(8, math.ceil(radius * 1.45))
        inner_x1 = max(0, math.floor(min(c.cx for c in all_c)) - pad)
        inner_y1 = max(0, math.floor(min(c.cy for c in all_c)) - pad)
        inner_x2 = min(w, math.ceil(max(c.cx for c in all_c)) + pad)
        inner_y2 = min(h, math.ceil(max(c.cy for c in all_c)) + pad)

        roi_x1 = inner_x1 - max_shift
        roi_y1 = inner_y1 - max_shift
        roi_x2 = inner_x2 + max_shift
        roi_y2 = inner_y2 + max_shift
        if roi_x1 < 0 or roi_y1 < 0 or roi_x2 > w or roi_y2 > h:
            return 0.0, 0.0

        tmpl_w = inner_x2 - inner_x1
        tmpl_h = inner_y2 - inner_y1
        if tmpl_w < 16 or tmpl_h < 16:
            return 0.0, 0.0

        roi = proc_gray[roi_y1:roi_y2, roi_x1:roi_x2]
        gx = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
        edge_mag = cv2.magnitude(gx, gy)
        edge_max = float(np.max(edge_mag))
        if edge_max < 1e-3:
            return 0.0, 0.0
        edge_norm = (edge_mag * (255.0 / edge_max)).astype(np.float32)

        ring_tmpl = np.zeros((tmpl_h, tmpl_w), dtype=np.float32)
        ring_r = max(3, round(radius))
        for c in all_c:
            lx = round(c.cx - inner_x1)
            ly = round(c.cy - inner_y1)
            cv2.circle(ring_tmpl, (lx, ly), ring_r, 255.0, 2, cv2.LINE_AA)

        res = cv2.matchTemplate(edge_norm, ring_tmpl, cv2.TM_CCOEFF_NORMED)
        zero_score = float(res[max_shift, max_shift])
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        best_score = float(max_val)

        if best_score < 0.14 or (best_score - zero_score) < 0.03:
            return 0.0, 0.0

        dx = float(max_loc[0] - max_shift)
        dy = float(max_loc[1] - max_shift)
        return dx, dy

    def measure_bubble(self, gray: np.ndarray, coord: BubbleCoord) -> BubbleReading:
        """Compute multi-feature optical scores for a single bubble coordinate."""
        cfg = self.config
        h, w = gray.shape[:2]
        cx = round(coord.cx)
        cy = round(coord.cy)
        half = max(4, math.ceil(coord.radius * cfg.ring_outer_ratio) + 1)

        # Pad ROI safely if bubble sits near the page edge
        x1, y1 = cx - half, cy - half
        x2, y2 = cx + half + 1, cy + half + 1
        pad_l = max(0, -x1)
        pad_t = max(0, -y1)
        pad_r = max(0, x2 - w)
        pad_b = max(0, y2 - h)

        patch = gray[max(0, y1) : min(h, y2), max(0, x1) : min(w, x2)]
        if pad_l or pad_t or pad_r or pad_b:
            patch = np.pad(
                patch,
                ((pad_t, pad_b), (pad_l, pad_r)),
                mode="edge",
            )

        inner_mask, ring_mask = _radial_masks(
            half,
            round(coord.radius, 1),
            cfg.inner_radius_ratio,
            cfg.ring_inner_ratio,
            cfg.ring_outer_ratio,
        )

        inner_px = patch[inner_mask].astype(np.float32)
        ring_px = patch[ring_mask].astype(np.float32)

        if inner_px.size == 0 or ring_px.size == 0:
            return BubbleReading(
                option=coord.option,
                cx=coord.cx,
                cy=coord.cy,
                radius=coord.radius,
                fill_ratio=0.0,
                darkness=0.0,
                ink_score=0.0,
                combined_score=0.0,
                selected=False,
            )

        # 75th percentile of outer ring ignores adjacent printed numbers/lines
        ring_bg = float(np.percentile(ring_px, 75))
        fill_ratio = float(np.mean(inner_px < (ring_bg - cfg.fill_delta)))
        darkness = float(
            np.clip((ring_bg - float(np.mean(inner_px))) / max(ring_bg, 1.0), 0.0, 1.0)
        )
        ink_score = float(np.mean(inner_px < (ring_bg - cfg.ink_delta)))

        combined = float(
            np.clip(
                0.44 * fill_ratio + 0.36 * darkness + 0.20 * min(1.0, ink_score * 2.2),
                0.0,
                1.0,
            )
        )

        return BubbleReading(
            option=coord.option,
            cx=coord.cx,
            cy=coord.cy,
            radius=coord.radius,
            fill_ratio=round(fill_ratio, 4),
            darkness=round(darkness, 4),
            ink_score=round(ink_score, 4),
            combined_score=round(combined, 4),
            selected=False,
        )

    def detect_sheet(
        self,
        warped_bgr: np.ndarray,
        template: Template,
    ) -> tuple[dict[str, FieldReading], list[ReviewItem]]:
        """Measure and classify every field block on an aligned sheet image."""
        cfg = template.detection
        # Use template-level detection config for this sheet
        self.config = cfg

        gray = ensure_grayscale(warped_bgr)
        proc = normalize_illumination(gray) if cfg.normalize_illumination else gray

        # First pass: measure all raw bubble features across the sheet
        measured_blocks: list[tuple[FieldBlock, list[tuple[str, list[BubbleReading]]]]] = []
        all_scores: list[float] = []

        for block in template.blocks:
            raw_fields = block.iter_field_bubbles()
            dx, dy = (
                self._estimate_block_offset(
                    proc, raw_fields, block.bubble_radius, cfg.local_refinement_px
                )
                if cfg.local_refinement and cfg.local_refinement_px > 0
                else (0.0, 0.0)
            )
            block_fields: list[tuple[str, list[BubbleReading]]] = []
            for field_id, coords in raw_fields:
                if dx != 0.0 or dy != 0.0:
                    shifted_coords = [
                        BubbleCoord(
                            field_id=c.field_id,
                            option=c.option,
                            cx=round(c.cx + dx, 2),
                            cy=round(c.cy + dy, 2),
                            radius=c.radius,
                        )
                        for c in coords
                    ]
                else:
                    shifted_coords = coords
                readings = [self.measure_bubble(proc, c) for c in shifted_coords]
                all_scores.extend(r.combined_score for r in readings)
                block_fields.append((field_id, readings))
            measured_blocks.append((block, block_fields))

        # Global baseline captures faint printed letters/borders inside unmarked bubbles
        global_baseline = float(np.percentile(all_scores, 35)) if len(all_scores) >= 10 else 0.05
        global_baseline = min(global_baseline, cfg.blank_floor * 0.9)

        fields_out: dict[str, FieldReading] = {}
        review_items: list[ReviewItem] = []

        for block, block_fields in measured_blocks:
            for field_id, readings in block_fields:
                field_reading, review = self._classify_field(
                    block=block,
                    field_id=field_id,
                    readings=readings,
                    global_baseline=global_baseline,
                    cfg=cfg,
                )
                fields_out[field_id] = field_reading
                if review is not None:
                    review_items.append(review)

        return fields_out, review_items

    def _classify_field(
        self,
        block: FieldBlock,
        field_id: str,
        readings: list[BubbleReading],
        global_baseline: float,
        cfg: DetectionConfig,
    ) -> tuple[FieldReading, ReviewItem | None]:
        scores = [r.combined_score for r in readings]
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        # Estimate local unmarked baseline (captures printed letters inside blank bubbles)
        if len(scores) >= 3:
            non_top = [scores[i] for i in ranked_indices[1:]]
            local_baseline = min(float(np.median(non_top)), cfg.fill_threshold * 0.95)
        else:
            local_baseline = min(global_baseline, cfg.fill_threshold * 0.95)

        effective_scores = [max(0.0, s - local_baseline) for s in scores]
        top_idx = ranked_indices[0]
        top_raw = scores[top_idx]
        top_eff = effective_scores[top_idx]
        top_dark = readings[top_idx].darkness
        second_idx = ranked_indices[1] if len(ranked_indices) > 1 else None
        second_raw = scores[second_idx] if second_idx is not None else 0.0
        second_eff = effective_scores[second_idx] if second_idx is not None else 0.0
        second_dark = readings[second_idx].darkness if second_idx is not None else 0.0
        gap = top_eff - second_eff

        # Darkness-dominant check: a dark solid mark next to a faint erased pencil smudge
        # exhibits a steep darkness drop even when binary fill_ratio saturates on the smudge.
        darkness_dominant_over_second = (
            second_idx is not None
            and top_dark >= 0.48
            and second_dark < top_dark * cfg.erased_dominance_ratio
        )
        effective_gap = (
            max(gap, (top_dark - second_dark) * 0.85) if darkness_dominant_over_second else gap
        )

        mark_delta_thresh = max(0.16, cfg.fill_threshold - 0.06)
        blank_delta_floor = max(0.08, cfg.blank_floor - 0.04)

        selected_indices: list[int] = []
        status: FieldStatus = "ok"
        confidence = 1.0
        review_msg = ""

        # Case 1: Clearly blank field
        if top_eff < blank_delta_floor and top_raw < (local_baseline + mark_delta_thresh):
            status = "blank"
            margin_below = max(0.0, (mark_delta_thresh - top_eff) / max(mark_delta_thresh, 1e-6))
            confidence = round(float(np.clip(0.84 + 0.15 * margin_below, 0.84, 0.99)), 4)

        # Case 2: Borderline faint mark or smudge
        elif top_eff < mark_delta_thresh:
            if effective_gap >= cfg.min_separation and readings[top_idx].ink_score >= 0.14:
                selected_indices = [top_idx]
                status = "low_confidence"
                confidence = round(
                    float(np.clip(0.55 + (top_eff / mark_delta_thresh) * 0.16, 0.45, 0.71)),
                    4,
                )
                review_msg = (
                    f"Faint or partial mark detected on '{readings[top_idx].option}' "
                    f"(delta={top_eff:.2f}, gap={effective_gap:.2f})."
                )
            else:
                status = "low_confidence"
                confidence = round(
                    float(
                        np.clip(0.68 - (top_eff / max(mark_delta_thresh, 1e-6)) * 0.20, 0.40, 0.70)
                    ),
                    4,
                )
                review_msg = (
                    f"Ambiguous faint smudge near '{readings[top_idx].option}' "
                    f"(delta={top_eff:.2f}); verify blank vs marked."
                )

        # Case 3: At least one bubble clearly stands out above unmarked baseline
        else:
            marked = [
                i
                for i in ranked_indices
                if effective_scores[i] >= mark_delta_thresh
                and effective_scores[i] >= top_eff * cfg.multi_mark_ratio
                and (
                    i == top_idx
                    or top_dark < 0.48
                    or readings[i].darkness >= top_dark * cfg.erased_dominance_ratio
                )
            ]
            if not marked:
                marked = [top_idx]

            if len(marked) > 1:
                selected_indices = sorted(marked)
                if block.allow_multiple:
                    status = "ok"
                    confidence = round(float(np.clip(0.82 + 0.16 * top_eff, 0.82, 0.98)), 4)
                else:
                    status = "multi_marked"
                    confidence = round(float(np.clip(0.35 + 0.25 * gap, 0.25, 0.60)), 4)
                    opts = ", ".join(readings[i].option for i in selected_indices)
                    review_msg = f"Multiple bubbles marked ({opts}) in single-choice field."
            else:
                selected_indices = [top_idx]
                strength = min(1.0, top_eff / max(mark_delta_thresh * 1.5, 1e-6))
                sep_score = min(1.0, effective_gap / max(cfg.min_separation * 1.5, 1e-6))
                confidence = round(
                    float(np.clip(0.45 + 0.30 * strength + 0.25 * sep_score, 0.45, 0.995)),
                    4,
                )
                if (
                    effective_gap < cfg.min_separation
                    or confidence < cfg.review_confidence_threshold
                ):
                    status = "low_confidence"
                    runner_up = readings[second_idx].option if second_idx is not None else "-"
                    review_msg = (
                        f"Low separation between '{readings[top_idx].option}' ({top_raw:.2f}) "
                        f"and '{runner_up}' ({second_raw:.2f})."
                    )
                else:
                    status = "ok"

        for idx in selected_indices:
            readings[idx].selected = True

        selected_options = [readings[i].option for i in selected_indices]
        value = "".join(selected_options) if selected_options else block.empty_value

        field_reading = FieldReading(
            field_id=field_id,
            block_name=block.name,
            value=value,
            selected_options=selected_options,
            confidence=confidence,
            status=status,
            bubbles=readings,
        )

        review_item: ReviewItem | None = None
        if status in {"low_confidence", "multi_marked"}:
            xs = [r.cx for r in readings]
            ys = [r.cy for r in readings]
            pad = max(18.0, block.bubble_radius * 2.2)
            bbox = (
                max(0, int(min(xs) - pad)),
                max(0, int(min(ys) - pad)),
                int(max(xs) + pad),
                int(max(ys) + pad),
            )
            review_item = ReviewItem(
                field_id=field_id,
                block_name=block.name,
                reason=status,
                suggested_value=value,
                confidence=confidence,
                candidate_options=[r.option for r in readings],
                bbox=bbox,
                message=review_msg,
            )

        return field_reading, review_item
