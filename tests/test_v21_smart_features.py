"""Tests for OMRKit v2.1 smart features: QR auto-scan, auto-grid finder, migration, and 1-click demo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from omrkit import (
    SheetGenerator,
    detect_layout_from_blank,
    get_sheet_preset,
    migrate_legacy_template_dict,
    scan_image_auto,
)
from omrkit.api import create_app
from omrkit.cli.app import app as cli_app
from omrkit.core.benchmark import apply_camera_distortion, render_synthetic_filled_sheet
from omrkit.io.loader import load_bytes, load_document

runner = CliRunner()
client = TestClient(create_app())


@pytest.mark.parametrize(
    "preset_id",
    ["quick_quiz_20", "standard_mcq_40", "turkish_exam_50", "turkish_yks_120"],
)
def test_qr_zero_template_auto_scan_rotated_and_warped(preset_id: str) -> None:
    spec = get_sheet_preset(preset_id)
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, f"{preset_id}.pdf", dpi=spec.dpi)[0].image_bgr

    answers = {"q1": "B", "q2": "D", "q3": "A", "q4": "C"}
    marked = render_synthetic_filled_sheet(blank, gen.template, answers, seed=88)
    distorted = apply_camera_distortion(
        marked, rotation_deg=90, perspective_strength=0.04, shadow_strength=0.22, seed=88
    )

    res, _ = scan_image_auto(distorted, source_name=f"{preset_id}_rot90.jpg")
    assert res.error is None
    assert res.template_name == preset_id
    for qid, expected in answers.items():
        assert res.fields[qid].value == expected


def test_auto_detect_bubble_grids_on_real_turkish_and_generated_blanks() -> None:
    # Real Turkish 50Q optical sheet blank
    tr_blank = load_document("examples/turkish_exam_50q/blank_form.jpg")[0].image_bgr
    tmpl_tr, cnt_tr = detect_layout_from_blank(tr_blank, "turkish_auto")
    assert cnt_tr >= 400
    assert len(tmpl_tr.blocks) == 4
    mcq_counts = sorted(len(b.expanded_labels()) for b in tmpl_tr.blocks if b.field_type == "mcq")
    id_counts = sorted(
        len(b.expanded_labels()) for b in tmpl_tr.blocks if b.field_type == "grid_digits"
    )
    assert mcq_counts == [25, 25]
    assert id_counts == [6, 11]

    # Generated ArUco 40Q sheet blank
    gen40 = SheetGenerator().generate(get_sheet_preset("standard_mcq_40"))
    b40 = load_bytes(gen40.pdf_bytes, "40.pdf", dpi=200)[0].image_bgr
    tmpl_40, cnt_40 = detect_layout_from_blank(b40, "std40_auto")
    assert cnt_40 >= 270
    assert len(tmpl_40.blocks) == 3


def test_legacy_omrchecker_template_migration(tmp_path: Path) -> None:
    legacy = {
        "pageDimensions": [2134, 1999],
        "bubbleDimensions": [50, 50],
        "customLabels": {"SINAV": ["s1", "s2", "s3"]},
        "fieldBlocks": {
            "ID_BLOCK": {
                "fieldType": "QTYPE_INT",
                "fieldLabels": ["s1", "s2", "s3"],
                "bubblesGap": 62,
                "labelsGap": 57,
                "origin": [93, 290],
            },
            "MCQ_BLOCK": {
                "fieldType": "QTYPE_MCQ5",
                "fieldLabels": ["q1..10"],
                "bubblesGap": 57,
                "labelsGap": 62,
                "origin": [1375, 233],
            },
        },
        "preProcessors": [
            {
                "name": "CropOnMarkers",
                "options": {"relativePath": "omr_marker.jpg", "sheetToMarkerWidthRatio": 17},
            }
        ],
    }
    migrated = migrate_legacy_template_dict(legacy, name="legacy_turkish")
    assert migrated.registration.mode == "markers"
    assert migrated.registration.marker_path == "omr_marker.jpg"
    assert len(migrated.blocks) == 2
    assert migrated.blocks[0].group_as == "SINAV"
    assert len(migrated.all_field_ids()) == 13

    # CLI migrate-template & detect-layout
    src_file = tmp_path / "old.json"
    dst_file = tmp_path / "new.json"
    src_file.write_text(json.dumps(legacy), encoding="utf-8")
    mig_res = runner.invoke(cli_app, ["migrate-template", str(src_file), "-o", str(dst_file)])
    assert mig_res.exit_code == 0
    assert dst_file.exists()

    det_file = tmp_path / "auto_detected.json"
    det_res = runner.invoke(
        cli_app,
        ["detect-layout", "examples/turkish_exam_50q/blank_form.jpg", "-o", str(det_file)],
    )
    assert det_res.exit_code == 0
    assert det_file.exists()


def test_v21_api_endpoints_auto_scan_auto_detect_migrate_and_demo() -> None:
    # 1. One-click demo cohort
    demo = client.post("/api/demo/cohort?preset_id=quick_quiz_20")
    assert demo.status_code == 200
    demo_data = demo.json()
    assert demo_data["scan_response"]["total_sheets"] == 5
    assert demo_data["scan_response"]["flagged_sheets"] >= 1
    assert demo_data["grading_report"]["analytics"]["student_count"] == 5

    # 2. Auto-detect layout via API
    blank_bytes = Path("examples/turkish_exam_50q/blank_form.jpg").read_bytes()
    auto_det = client.post(
        "/api/templates/auto-detect",
        files={"file": ("blank_form.jpg", blank_bytes, "image/jpeg")},
    )
    assert auto_det.status_code == 200
    assert auto_det.json()["blocks_count"] == 4

    # 3. Auto-scan via QR (template_json="auto")
    spec = get_sheet_preset("quick_quiz_20")
    gen = SheetGenerator().generate(spec)
    scan_auto_res = client.post(
        "/api/scan",
        files=[("files", ("quiz.pdf", gen.pdf_bytes, "application/pdf"))],
        data={"template_json": "auto", "include_overlay": "true"},
    )
    assert scan_auto_res.status_code == 200
    assert scan_auto_res.json()["sheets"][0]["template_name"] == "quick_quiz_20"
    assert scan_auto_res.json()["failed_sheets"] == 0

    # 4. Migrate legacy template via API
    mig = client.post(
        "/api/templates/migrate",
        json={
            "name": "migrated_api",
            "legacy_template": {
                "pageDimensions": [400, 500],
                "bubbleDimensions": [20, 20],
                "fieldBlocks": {
                    "B1": {
                        "fieldType": "QTYPE_MCQ4",
                        "fieldLabels": ["q1..5"],
                        "bubblesGap": 40,
                        "labelsGap": 45,
                        "origin": [50, 60],
                    }
                },
            },
        },
    )
    assert mig.status_code == 200
    assert mig.json()["template"]["name"] == "migrated_api"
