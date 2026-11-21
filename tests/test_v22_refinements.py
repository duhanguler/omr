"""Regression and benchmark tests for OMRKit v2.2 refinements."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from omrkit.api.app import create_app
from omrkit.core.scanner import OMRScanner
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import get_sheet_preset
from omrkit.io.exporters import export_pdf_scorecard
from omrkit.io.loader import load_document
from omrkit.io.pdf_fonts import PdfFontPair, get_pdf_fonts
from omrkit.models.grading import QuestionVerdict, StudentGrade
from omrkit.models.template import BubbleCoord, RegistrationConfig, Template
from omrkit.vision.detector import HybridBubbleDetector
from omrkit.vision.grid_finder import detect_layout_from_blank
from omrkit.vision.preprocess import normalize_illumination


def _render_preset_blank(preset_id: str, tmp_path: Path):
    spec = get_sheet_preset(preset_id)
    generated = SheetGenerator().generate(spec)
    pdf_path = tmp_path / f"{preset_id}.pdf"
    pdf_path.write_bytes(generated.pdf_bytes)
    docs = load_document(pdf_path, dpi=200)
    assert len(docs) == 1
    return docs[0].image_bgr, generated.template, generated.sample_answer_key


def _field_coords(template: Template) -> dict[str, list[BubbleCoord]]:
    return {fid: coords for blk in template.blocks for fid, coords in blk.iter_field_bubbles()}


def _fill_bubble(img: np.ndarray, cx: float, cy: float, radius: float, tone: int) -> None:
    cv2.circle(img, (round(cx), round(cy)), max(2, round(radius * 0.78)), (tone, tone, tone), -1)


def test_erased_smudge_vs_double_mark_and_light_pencil(tmp_path: Path) -> None:
    """Reject erased gray smudges while still catching real double marks and light HB pencil."""
    blank, template, sample_key = _render_preset_blank("standard_mcq_40", tmp_path)
    scanner = OMRScanner(template)
    answers = sample_key.answers
    coords_by_field = _field_coords(template)

    # Case A: Dark intended mark (tone=45) + faint erased pencil smudge (tone=170)
    erased_img = blank.copy()
    for qid, expected in answers.items():
        expected_opt = expected if isinstance(expected, str) else expected[0]
        coords = coords_by_field[qid]
        smudge_opt = next(c.option for c in coords if c.option != expected_opt)
        for c in coords:
            if c.option == expected_opt:
                _fill_bubble(erased_img, c.cx, c.cy, c.radius, tone=45)
            elif c.option == smudge_opt:
                _fill_bubble(erased_img, c.cx, c.cy, c.radius, tone=170)

    res_erased, _ = scanner.scan_image(erased_img, source_name="erased_test.jpg")
    correct_erased = sum(1 for qid, exp in answers.items() if res_erased.fields[qid].value == exp)
    mcq_flags = [r for r in res_erased.review_items if r.field_id in answers]
    assert correct_erased == len(answers)
    assert mcq_flags == []

    # Case B: True double-mark (two dark fills tone=45 and tone=55)
    double_img = blank.copy()
    for qid, expected in answers.items():
        expected_opt = expected if isinstance(expected, str) else expected[0]
        coords = coords_by_field[qid]
        second_opt = next(c.option for c in coords if c.option != expected_opt)
        for c in coords:
            if c.option == expected_opt:
                _fill_bubble(double_img, c.cx, c.cy, c.radius, tone=45)
            elif c.option == second_opt:
                _fill_bubble(double_img, c.cx, c.cy, c.radius, tone=55)

    res_double, _ = scanner.scan_image(double_img, source_name="double_test.jpg")
    multi_count = sum(1 for qid in answers if res_double.fields[qid].status == "multi_marked")
    assert multi_count == len(answers)

    # Case C: Light HB pencil mark (tone=155) alone should still be detected cleanly
    light_img = blank.copy()
    for qid, expected in answers.items():
        expected_opt = expected if isinstance(expected, str) else expected[0]
        for c in coords_by_field[qid]:
            if c.option == expected_opt:
                _fill_bubble(light_img, c.cx, c.cy, c.radius, tone=155)

    res_light, _ = scanner.scan_image(light_img, source_name="light_pencil.jpg")
    correct_light = sum(1 for qid, exp in answers.items() if res_light.fields[qid].value == exp)
    assert correct_light == len(answers)


@pytest.mark.parametrize("occlude_idx", [0, 1, 2, 3])
def test_aruco_3_of_4_occluded_corner_recovery(tmp_path: Path, occlude_idx: int) -> None:
    """Recover full 120/120 accuracy even when any 1 of 4 ArUco markers is occluded + rotated 90°."""
    blank, template, sample_key = _render_preset_blank("turkish_yks_120", tmp_path)
    answers = sample_key.answers
    coords_by_field = _field_coords(template)

    marked = blank.copy()
    for qid, expected in answers.items():
        expected_opt = expected if isinstance(expected, str) else expected[0]
        for c in coords_by_field[qid]:
            if c.option == expected_opt:
                _fill_bubble(marked, c.cx, c.cy, c.radius, tone=40)

    # Occlude one canonical corner marker (TL=0, TR=1, BR=2, BL=3) with a simulated thumb patch
    h, w = marked.shape[:2]
    corner_boxes = [
        (0, 0, 220, 220),
        (w - 220, 0, w, 220),
        (w - 220, h - 220, w, h),
        (0, h - 220, 220, h),
    ]
    x1, y1, x2, y2 = corner_boxes[occlude_idx]
    cv2.rectangle(marked, (x1, y1), (x2, y2), (215, 200, 185), -1)

    # Rotate 90° clockwise and apply mild perspective skew
    rot = cv2.rotate(marked, cv2.ROTATE_90_CLOCKWISE)
    rh, rw = rot.shape[:2]
    src_pts = np.array([[0, 0], [rw - 1, 0], [rw - 1, rh - 1], [0, rh - 1]], dtype=np.float32)
    dst_pts = np.array(
        [[28, 18], [rw - 36, 42], [rw - 16, rh - 24], [40, rh - 34]], dtype=np.float32
    )
    mat = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped_in = cv2.warpPerspective(rot, mat, (rw, rh), borderValue=(230, 230, 230))

    result, _ = OMRScanner(template).scan_image(
        warped_in, source_name=f"occluded_{occlude_idx}.jpg"
    )
    assert result.error is None
    assert result.registration_method == "aruco_3pt"
    assert result.registration_score >= 0.9
    assert any("3 visible markers" in w_msg for w_msg in result.warnings)

    correct = sum(1 for qid, exp in answers.items() if result.fields[qid].value == exp)
    assert correct == len(answers)


def test_block_micro_alignment_photocopy_drift(tmp_path: Path) -> None:
    """Snap photocopy-drifted (+6, +3 px) blocks back onto exact bubble centers."""
    blank, template, sample_key = _render_preset_blank("turkish_yks_120", tmp_path)
    answers = sample_key.answers
    coords_by_field = _field_coords(template)

    marked = blank.copy()
    for qid, expected in answers.items():
        expected_opt = expected if isinstance(expected, str) else expected[0]
        for c in coords_by_field[qid]:
            if c.option == expected_opt:
                _fill_bubble(marked, c.cx, c.cy, c.radius, tone=40)

    # Simulate pure photocopy translation shift of (+6, +3) px without ArUco re-warping
    shift_m = np.array([[1.0, 0.0, 6.0], [0.0, 1.0, 3.0]], dtype=np.float32)
    drifted = cv2.warpAffine(
        marked, shift_m, (marked.shape[1], marked.shape[0]), borderValue=(255, 255, 255)
    )

    flat_template = template.model_copy(update={"registration": RegistrationConfig(mode="none")})
    result, _ = OMRScanner(flat_template).scan_image(drifted, source_name="photocopy_drift.jpg")
    correct = sum(1 for qid, exp in answers.items() if result.fields[qid].value == exp)
    assert correct == len(answers)

    # Also assert _estimate_block_offset directly recovers the exact (+6, +3) translation
    proc_gray = normalize_illumination(cv2.cvtColor(drifted, cv2.COLOR_BGR2GRAY))
    mcq_block = next(b for b in flat_template.blocks if b.name.startswith("MCQ"))
    dx, dy = HybridBubbleDetector._estimate_block_offset(
        proc_gray, mcq_block.iter_field_bubbles(), mcq_block.bubble_radius, max_shift=6
    )
    assert abs(dx - 6.0) <= 1.0
    assert abs(dy - 3.0) <= 1.0


def test_grid_finder_auto_deskew(tmp_path: Path) -> None:
    """Auto-deskew a 2.8-degree tilted blank form so grid finder extracts exact clean blocks."""
    blank, _, _ = _render_preset_blank("standard_mcq_40", tmp_path)
    h, w = blank.shape[:2]
    rot_m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 2.8, 1.0)
    tilted = cv2.warpAffine(blank, rot_m, (w, h), borderValue=(255, 255, 255))

    detected_template, detected_count = detect_layout_from_blank(
        tilted, template_name="tilted_standard_40"
    )
    assert detected_count > 200
    assert len(detected_template.blocks) == 3
    assert len(detected_template.all_field_ids()) == 48


def test_unicode_pdf_fonts_and_turkish_scorecard(tmp_path: Path) -> None:
    """Verify native Unicode TrueType font discovery, Turkish sheet PDF, and Turkish scorecard PDF."""
    fonts = get_pdf_fonts()
    assert fonts.regular in {"OMRKitSans", "Helvetica"}
    if fonts.unicode_ready:
        assert fonts.format_text("OPTİK CEVAP KAĞIDI — Öğrenci") == "OPTİK CEVAP KAĞIDI — Öğrenci"

    # ASCII fallback path when unicode_ready=False
    ascii_pair = PdfFontPair(regular="Helvetica", bold="Helvetica-Bold", unicode_ready=False)
    assert ascii_pair.format_text("OPTİK ŞĞÜÖÇ") == "OPTIK SGUOC"

    # Generate Turkish preset PDF and ensure pypdfium2 rasterizes it cleanly
    spec = get_sheet_preset("turkish_exam_50")
    assert "OPTİK" in spec.title
    pdf_path = tmp_path / "turkish_exam_50.pdf"
    pdf_path.write_bytes(SheetGenerator().generate(spec).pdf_bytes)
    docs = load_document(pdf_path, dpi=150)
    assert len(docs) == 1
    assert docs[0].image_bgr.shape[0] > 1000

    # Generate Turkish student scorecard PDF
    grade = StudentGrade(
        sheet_id="ogrenci_01",
        source_file="ogrenci_01.jpg",
        booklet="A",
        student_metadata={"TC Kimlik No": "10000000146", "Öğrenci": "Çağrı Şahin"},  # noqa: RUF001
        total_questions=20,
        raw_score=18.75,
        max_score=20.0,
        percentage=93.75,
        correct=19,
        incorrect=1,
        blank=0,
        verdicts=[
            QuestionVerdict(
                question_id="q1",
                expected="A",
                marked="A",
                points=1.0,
                verdict="correct",
                confidence=0.99,
            )
        ],
    )
    scorecard_path = tmp_path / "turkish_scorecard.pdf"
    export_pdf_scorecard(grade, scorecard_path, exam_name="YKS Deneme — Türkçe & Matematik")
    raw_pdf = scorecard_path.read_bytes()
    assert raw_pdf.startswith(b"%PDF-")
    card_docs = load_document(scorecard_path, dpi=120)
    assert len(card_docs) == 1


def test_api_scan_and_demo_return_review_crops_and_dimensions(tmp_path: Path) -> None:
    """Verify /api/demo/cohort and /api/scan emit magnified HITL review_crops and sheet_dimensions."""
    client = TestClient(create_app())

    # 1. Demo cohort includes a multi-marked sheet with review crops + dimensions
    demo_res = client.post("/api/demo/cohort?preset_id=quick_quiz_20")
    assert demo_res.status_code == 200
    demo_payload = demo_res.json()
    scan_resp = demo_payload["scan_response"]
    assert "review_crops" in scan_resp
    assert "sheet_dimensions" in scan_resp
    flagged_sheets = [s for s in scan_resp["sheets"] if s["review_items"]]
    assert len(flagged_sheets) >= 1
    for sheet in flagged_sheets:
        sid = sheet["sheet_id"]
        assert sid in scan_resp["sheet_dimensions"]
        w, h = scan_resp["sheet_dimensions"][sid]
        assert w > 500 and h > 500
        crops = scan_resp["review_crops"].get(sid, {})
        for item in sheet["review_items"]:
            if item["bbox"] is not None:
                data_url = crops[item["field_id"]]
                assert data_url.startswith("data:image/jpeg;base64,")
                decoded = base64.b64decode(data_url.split(",", 1)[1])
                assert decoded[:2] == b"\xff\xd8"

    # 2. Direct /api/scan with a deliberately multi-marked image returns review_crops
    blank, template, _ = _render_preset_blank("quick_quiz_20", tmp_path)
    q1_coords = _field_coords(template)["q1"]
    _fill_bubble(blank, q1_coords[0].cx, q1_coords[0].cy, q1_coords[0].radius, tone=40)
    _fill_bubble(blank, q1_coords[1].cx, q1_coords[1].cy, q1_coords[1].radius, tone=40)
    ok, encoded = cv2.imencode(".jpg", blank)
    assert ok

    scan_res = client.post(
        "/api/scan",
        data={"template_json": json.dumps(template.model_dump(mode="json"))},
        files=[("files", ("double_q1.jpg", encoded.tobytes(), "image/jpeg"))],
    )
    assert scan_res.status_code == 200
    body = scan_res.json()
    sheet_id = body["sheets"][0]["sheet_id"]
    assert body["sheet_dimensions"][sheet_id] == [template.page_width, template.page_height]
    assert "q1" in body["review_crops"][sheet_id]
    assert body["review_crops"][sheet_id]["q1"].startswith("data:image/jpeg;base64,")
