"""Tests for all 5 registration engines (ArUco, markers, page_quad, homography, none)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from omrkit.core.benchmark import apply_camera_distortion, render_synthetic_filled_sheet
from omrkit.core.scanner import OMRScanner
from omrkit.generator import SheetGenerator, get_sheet_preset
from omrkit.io.loader import load_bytes, load_document
from omrkit.models import FieldBlock, RegistrationConfig, Template
from omrkit.vision.preprocess import rotate_image
from omrkit.vision.registration import RegistrationError, register_sheet


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_aruco_registration_auto_orients_all_rotations(rotation: int) -> None:
    spec = get_sheet_preset("quick_quiz_20")
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "quiz.pdf", dpi=spec.dpi)[0].image_bgr
    answers = {f"q{i}": spec.options[i % 4] for i in range(1, 21)}
    for i in range(1, 7):
        answers[f"student_id_{i}"] = str((i * 3) % 10)

    filled = render_synthetic_filled_sheet(blank, gen.template, answers, seed=42 + rotation)
    distorted = apply_camera_distortion(
        filled, rotation_deg=rotation, perspective_strength=0.04, shadow_strength=0.22, seed=7
    )

    result, _ = OMRScanner(gen.template).scan_image(distorted, source_name=f"rot_{rotation}.jpg")
    assert result.error is None
    assert result.registration_method == "aruco"
    for fid, expected in answers.items():
        assert result.fields[fid].value == expected


def test_real_turkish_exam_markers_and_auto_rotate() -> None:
    tmpl_path = Path("examples/turkish_exam_50q/template.json")
    scan_path = Path("examples/turkish_exam_50q/scans/20200814_133550.jpg")
    template = Template.from_file(tmpl_path)
    scanner = OMRScanner(template)

    # Normal upright EXIF-free real scan
    res = scanner.scan_file(scan_path)[0]
    assert res.error is None
    assert res.registration_method == "markers"
    assert res.grouped_values["SINAV_KODU"] == "190735"
    assert res.grouped_values["TC_KIMLIK_NO"] == "46918500273"

    # Rotate the real photo 90 degrees and verify auto_rotate recovers it
    page = load_document(scan_path)[0]
    rotated_90 = rotate_image(page.image_bgr, 90)
    res_rot, _ = scanner.scan_image(rotated_90, source_name="rotated_real.jpg")
    assert res_rot.error is None
    assert res_rot.grouped_values["SINAV_KODU"] == "190735"
    assert res_rot.grouped_values["TC_KIMLIK_NO"] == "46918500273"


def test_page_quad_registration() -> None:
    # Draw white sheet on dark desk with perspective skew
    sheet = np.full((600, 450, 3), 250, dtype=np.uint8)
    cv2.circle(sheet, (120, 120), 18, (25, 25, 25), -1)
    desk = np.full((800, 650, 3), 35, dtype=np.uint8)
    desk[100:700, 100:550] = sheet

    tmpl = Template(
        name="quad_test",
        page_width=450,
        page_height=600,
        registration=RegistrationConfig(mode="page_quad"),
        blocks=[
            FieldBlock(
                name="B1",
                origin=(120, 120),
                bubble_radius=18,
                bubbles_gap=60,
                labels_gap=60,
                options=["A", "B", "C"],
                labels=["q1"],
            )
        ],
    )
    reg = register_sheet(desk, tmpl)
    assert reg.method == "page_quad"
    assert reg.warped_bgr.shape[:2] == (600, 450)


def test_orb_homography_registration(tmp_path: Path) -> None:
    spec = get_sheet_preset("quick_quiz_20")
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "ref.pdf", dpi=spec.dpi)[0].image_bgr
    ref_path = tmp_path / "reference.png"
    cv2.imwrite(str(ref_path), blank)

    tmpl = gen.template.model_copy(
        update={
            "registration": RegistrationConfig(
                mode="homography", reference_path=str(ref_path), max_features=1500
            )
        }
    )
    shifted = apply_camera_distortion(blank, perspective_strength=0.02, seed=99)
    reg = register_sheet(shifted, tmpl)
    assert reg.method == "homography"
    assert reg.warped_bgr.shape[:2] == (tmpl.page_height, tmpl.page_width)


def test_aruco_registration_raises_on_blank_noise_image() -> None:
    spec = get_sheet_preset("quick_quiz_20")
    gen = SheetGenerator().generate(spec)
    blank = np.full((500, 500, 3), 240, dtype=np.uint8)
    with pytest.raises(RegistrationError, match="ArUco registration failed"):
        register_sheet(blank, gen.template)
