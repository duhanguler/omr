"""Annotated visual overlays for scan verification and graded sheet review."""

from __future__ import annotations

import cv2
import numpy as np

from omrkit.models.grading import StudentGrade
from omrkit.models.scan import SheetResult

# BGR color constants
_CLR_OK = (95, 138, 15)  # Emerald green
_CLR_WARN = (6, 119, 217)  # Amber
_CLR_ERR = (38, 38, 220)  # Crimson red
_CLR_BLANK = (165, 165, 165)  # Neutral gray
_CLR_EXPECTED = (205, 115, 25)  # Steel blue
_CLR_INK = (31, 24, 20)


def render_annotated_sheet(
    warped_bgr: np.ndarray,
    result: SheetResult,
    grade: StudentGrade | None = None,
) -> np.ndarray:
    """Draw color-coded optical readings, confidence signals, and optional grading feedback."""
    canvas = warped_bgr.copy()
    verdict_map = {v.question_id: v for v in grade.verdicts} if grade is not None else {}

    for field_id, reading in result.fields.items():
        verdict = verdict_map.get(field_id)

        for bubble in reading.bubbles:
            cx, cy = round(bubble.cx), round(bubble.cy)
            r = max(4, round(bubble.radius))

            if verdict is not None:
                is_expected = bubble.option in verdict.expected
                if bubble.selected and verdict.verdict in {"correct", "bonus"}:
                    cv2.circle(canvas, (cx, cy), r + 2, _CLR_OK, 3, cv2.LINE_AA)
                elif bubble.selected and verdict.verdict == "incorrect":
                    cv2.circle(canvas, (cx, cy), r + 2, _CLR_ERR, 3, cv2.LINE_AA)
                elif is_expected and verdict.verdict in {"incorrect", "blank"}:
                    cv2.circle(canvas, (cx, cy), r + 2, _CLR_EXPECTED, 2, cv2.LINE_AA)
                else:
                    cv2.circle(canvas, (cx, cy), r, _CLR_BLANK, 1, cv2.LINE_AA)
                continue

            if bubble.selected:
                if reading.status == "multi_marked":
                    color = _CLR_ERR
                elif reading.status == "low_confidence":
                    color = _CLR_WARN
                else:
                    color = _CLR_OK
                cv2.circle(canvas, (cx, cy), r + 2, color, 3, cv2.LINE_AA)
                cv2.putText(
                    canvas,
                    bubble.option,
                    (cx - r // 2, cy - r - 4),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    1,
                    cv2.LINE_AA,
                )
            else:
                border_color = _CLR_WARN if reading.status == "low_confidence" else _CLR_BLANK
                cv2.circle(canvas, (cx, cy), r, border_color, 1, cv2.LINE_AA)

    # Compact status header banner
    banner_h = 44
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 0), (canvas.shape[1], banner_h), (246, 249, 250), -1)
    cv2.addWeighted(overlay, 0.88, canvas, 0.12, 0, canvas)
    cv2.line(canvas, (0, banner_h), (canvas.shape[1], banner_h), (210, 215, 220), 1)

    if grade is not None:
        header = (
            f"OMRKit | {result.source_file} | Score: {grade.raw_score:.2f}/{grade.max_score:.2f} "
            f"({grade.percentage:.1f}%) | +{grade.correct} -{grade.incorrect} o{grade.blank}"
        )
    else:
        header = (
            f"OMRKit | {result.source_file} | Conf: {result.overall_confidence * 100:.1f}% "
            f"| Review Flags: {len(result.review_items)} | Reg: {result.registration_method}"
        )

    cv2.putText(
        canvas,
        header,
        (16, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        _CLR_INK,
        1,
        cv2.LINE_AA,
    )
    result_img: np.ndarray = canvas
    return result_img
