"""Regression tests for the v2.1.1 security audit and full-stack bug hunt."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from omrkit._version import __version__
from omrkit.api.app import create_app
from omrkit.cli.app import app as cli_app
from omrkit.core.migrator import migrate_legacy_template_dict
from omrkit.core.scanner import OMRScanner, ensure_unique_sheet_ids
from omrkit.core.validators import validate_digits, validate_luhn, validate_tr_tckn
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import SheetSpec
from omrkit.grading.grader import ExamGrader
from omrkit.io.exporters import export_pdf_scorecard_bytes
from omrkit.io.loader import DocumentLoadError, load_bytes
from omrkit.models.grading import AnswerKey, GradingPolicy, QuestionVerdict, StudentGrade
from omrkit.models.scan import BubbleReading, FieldReading, ReviewItem, SheetResult
from omrkit.models.template import (
    FieldBlock,
    RegistrationConfig,
    Template,
    expand_field_labels,
)
from omrkit.vision.registration import order_quad_points


def _tiny_png_bytes() -> bytes:
    img = np.full((240, 240, 3), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


# ---------------------------------------------------------------------------
# Security & DoS Regressions (SEC-1 .. SEC-4)
# ---------------------------------------------------------------------------


def test_sec1_api_scan_blocks_local_marker_and_reference_paths() -> None:
    client = TestClient(create_app())
    png = _tiny_png_bytes()

    for reg in (
        {"mode": "markers", "marker_path": "/etc/passwd"},
        {"mode": "homography", "reference_path": "/etc/hosts"},
    ):
        tmpl = {
            "name": "probe",
            "page_width": 400,
            "page_height": 400,
            "registration": reg,
            "blocks": [
                {
                    "name": "B1",
                    "origin": [100, 100],
                    "bubble_radius": 10,
                    "bubbles_gap": 30,
                    "labels_gap": 30,
                    "options": ["A", "B"],
                    "labels": ["q1"],
                }
            ],
        }
        resp = client.post(
            "/api/scan",
            files=[("files", ("t.png", png, "image/png"))],
            data={"template_json": json.dumps(tmpl)},
        )
        assert resp.status_code == 400
        assert "disabled on the HTTP API" in resp.json()["detail"]


def test_sec2_range_expansion_and_template_bounds_prevent_oom_dos() -> None:
    with pytest.raises(ValueError, match="exceeding the maximum"):
        expand_field_labels(["q1..10000000"])

    # Digit-containing prefixes now work cleanly (BUG-21)
    assert expand_field_labels(["sec1_q1..3"]) == ["sec1_q1", "sec1_q2", "sec1_q3"]

    with pytest.raises(ValidationError):
        Template(
            name="huge_page",
            page_width=50000,
            page_height=50000,
            registration=RegistrationConfig(mode="none"),
            blocks=[
                FieldBlock(
                    name="B1",
                    origin=(100, 100),
                    bubble_radius=10,
                    bubbles_gap=30,
                    labels_gap=30,
                    options=["A", "B"],
                    labels=["q1"],
                )
            ],
        )


def test_sec3_api_rejects_out_of_bounds_dpi_and_loader_checks_dpi() -> None:
    client = TestClient(create_app())
    png = _tiny_png_bytes()
    resp = client.post(
        "/api/preview-image",
        files={"file": ("sheet.png", png, "image/png")},
        data={"dpi": "50000"},
    )
    assert resp.status_code == 422

    # Direct PDF loader DPI guard
    pdf_bytes = (
        SheetGenerator().generate(SheetSpec(num_questions=10, questions_per_column=5)).pdf_bytes
    )
    with pytest.raises(DocumentLoadError, match="Invalid DPI"):
        load_bytes(pdf_bytes, "sheet.pdf", dpi=5000)


def test_sec4_turkish_and_header_injection_filenames_are_sanitized() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/export/scorecard",
        json={
            "exam_name": "Türkçe Deneme",
            "grade": {
                "sheet_id": 'öğrenci_şahin"\r\nX-Injected: 1',
                "source_file": "öğrenci_şahin.jpg",
                "total_questions": 1,
                "correct": 1,
                "raw_score": 1.0,
                "max_score": 1.0,
                "percentage": 100.0,
                "verdicts": [],
            },
        },
    )
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert "\r" not in cd and "\n" not in cd
    assert "ogrenci_sahin" in cd
    assert cd.endswith('_scorecard.pdf"')


# ---------------------------------------------------------------------------
# High & Medium Functional Regressions (BUG-5 .. BUG-24)
# ---------------------------------------------------------------------------


def test_bug5_sheet_spec_rejects_column_overflow_cleanly(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="exceeding the 4-column page limit"):
        SheetSpec(num_questions=120, questions_per_column=10)

    client = TestClient(create_app())
    resp = client.post("/api/generate", json={"num_questions": 120, "questions_per_column": 10})
    assert resp.status_code == 422

    # CLI auto-adjusts rows/column when overriding --questions
    runner = CliRunner()
    out_dir = tmp_path / "out_100"
    res = runner.invoke(
        cli_app,
        ["generate", "--preset", "quick_quiz_20", "--questions", "100", "-o", str(out_dir)],
    )
    assert res.exit_code == 0, res.output
    assert (out_dir / "quick_quiz_20_sheet.pdf").exists()


def test_bug6_order_quad_points_handles_45_degree_diamond() -> None:
    diamond = np.array([[100, 0], [200, 100], [100, 200], [0, 100]], dtype=np.float32)
    ordered = order_quad_points(diamond)
    assert ordered.shape == (4, 2)
    assert len({tuple(p) for p in ordered}) == 4
    # Must be clockwise with positive signed shoelace area in Y-down image coordinates
    x = ordered[:, 0]
    y = ordered[:, 1]
    area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    assert area > 0


def test_bug8_duplicate_sheet_ids_are_disambiguated_in_batch_and_api() -> None:
    s1 = SheetResult(sheet_id="exam", source_file="exam.jpg", template_name="t")
    s2 = SheetResult(sheet_id="exam", source_file="exam.png", template_name="t")
    s3 = SheetResult(sheet_id="exam", source_file="sub/exam.jpg", template_name="t")
    ensure_unique_sheet_ids([s1, s2, s3])
    assert [s1.sheet_id, s2.sheet_id, s3.sheet_id] == ["exam", "exam_2", "exam_3"]

    client = TestClient(create_app())
    png = _tiny_png_bytes()
    tmpl = {
        "name": "dup_test",
        "page_width": 240,
        "page_height": 240,
        "registration": {"mode": "none"},
        "blocks": [
            {
                "name": "B1",
                "origin": [60, 60],
                "bubble_radius": 10,
                "bubbles_gap": 30,
                "labels_gap": 30,
                "options": ["A", "B"],
                "labels": ["q1"],
            }
        ],
    }
    resp = client.post(
        "/api/scan",
        files=[
            ("files", ("same.jpg", png, "image/jpeg")),
            ("files", ("same.png", png, "image/png")),
        ],
        data={"template_json": json.dumps(tmpl)},
    )
    assert resp.status_code == 200
    body = resp.json()
    ids = [s["sheet_id"] for s in body["sheets"]]
    assert len(set(ids)) == 2
    assert set(body["overlays"].keys()) == set(ids)


def test_bug9_apply_override_updates_bubbles_and_overall_confidence() -> None:
    sheet = SheetResult(
        sheet_id="s1",
        source_file="s1.png",
        template_name="t",
        overall_confidence=0.65,
        fields={
            "q1": FieldReading(
                field_id="q1",
                block_name="B",
                value="AB",
                selected_options=["A", "B"],
                confidence=0.30,
                status="multi_marked",
                bubbles=[
                    BubbleReading(
                        option="A",
                        cx=10,
                        cy=10,
                        radius=8,
                        fill_ratio=0.9,
                        darkness=0.8,
                        ink_score=0.9,
                        combined_score=0.85,
                        selected=True,
                    ),
                    BubbleReading(
                        option="B",
                        cx=40,
                        cy=10,
                        radius=8,
                        fill_ratio=0.8,
                        darkness=0.7,
                        ink_score=0.8,
                        combined_score=0.75,
                        selected=True,
                    ),
                ],
            ),
            "q2": FieldReading(
                field_id="q2",
                block_name="B",
                value="C",
                selected_options=["C"],
                confidence=1.0,
                status="ok",
                bubbles=[],
            ),
        },
        review_items=[
            ReviewItem(
                field_id="q1",
                block_name="B",
                reason="multi_marked",
                suggested_value="AB",
                confidence=0.30,
                candidate_options=["A", "B"],
                bbox=(0, 0, 50, 20),
                message="Multiple marks",
            )
        ],
    )
    sheet.apply_override("q1", "B")
    assert sheet.fields["q1"].value == "B"
    assert sheet.fields["q1"].bubbles[0].selected is False
    assert sheet.fields["q1"].bubbles[1].selected is True
    assert sheet.overall_confidence == 1.0
    assert sheet.review_items == []


def test_bug11_cli_grade_supports_raw_json_list(tmp_path: Path) -> None:
    sheet = SheetResult(
        sheet_id="s1",
        source_file="s1.png",
        template_name="t",
        fields={"q1": FieldReading(field_id="q1", block_name="B", value="A", confidence=0.99)},
    )
    res_file = tmp_path / "list_results.json"
    res_file.write_text(json.dumps([sheet.model_dump(mode="json")]), encoding="utf-8")
    key_file = tmp_path / "key.json"
    AnswerKey(exam_name="List Test", answers={"q1": "A"}).to_file(key_file)

    runner = CliRunner()
    out_dir = tmp_path / "out"
    res = runner.invoke(cli_app, ["grade", str(res_file), "-k", str(key_file), "-o", str(out_dir)])
    assert res.exit_code == 0, res.output
    assert (out_dir / "graded_report.json").exists()


def test_bug12_validators_reject_unicode_superscript_digits_without_crashing() -> None:
    assert validate_tr_tckn("1234567890²") is False
    assert validate_luhn("42²") is False
    assert validate_digits("12²") is False
    assert validate_digits("١٢٣") is False


def test_bug13_and_bug23_api_error_codes_and_turkish_demo_cohort() -> None:
    client = TestClient(create_app())

    r_demo_bad = client.post("/api/demo/cohort?preset_id=does_not_exist")
    assert r_demo_bad.status_code == 400

    r_grade_bad = client.post(
        "/api/grade",
        json={
            "sheets": [],
            "answer_key": {"exam_name": "T", "answers": {"q1": "A"}},
            "policy": {"bonus_questions": ["q10..5"]},
        },
    )
    assert r_grade_bad.status_code == 422

    # Turkish 50Q demo cohort produces valid TC Kimlik numbers (no invalid_checksum flags)
    r_tr_demo = client.post("/api/demo/cohort?preset_id=turkish_exam_50")
    assert r_tr_demo.status_code == 200
    for s in r_tr_demo.json()["scan_response"]["sheets"]:
        tckn = s["grouped_values"].get("TC_KIMLIK_NO", "")
        assert validate_tr_tckn(tckn), f"Invalid demo TCKN: {tckn}"

    # Health endpoint reports single-source __version__
    assert client.get("/api/health").json()["version"] == __version__


def test_bug17_ungrouped_validator_emits_hitl_review_item() -> None:
    tmpl = Template(
        name="req_booklet",
        page_width=300,
        page_height=300,
        registration=RegistrationConfig(mode="none"),
        blocks=[
            FieldBlock(
                name="BOOKLET_BLK",
                origin=(60, 60),
                bubble_radius=12,
                bubbles_gap=36,
                labels_gap=36,
                options=["A", "B", "C", "D"],
                labels=["BOOKLET"],
                validator="non_empty",
            )
        ],
    )
    blank = np.full((300, 300, 3), 255, dtype=np.uint8)
    result, _ = OMRScanner(tmpl).scan_image(blank, source_name="blank.png")
    assert result.fields["BOOKLET"].status == "invalid_checksum"
    assert any(
        r.field_id == "BOOKLET" and r.reason == "invalid_checksum" for r in result.review_items
    )


def test_bug19_partial_credit_cannot_be_gamed_by_marking_all_options() -> None:
    key = AnswerKey(exam_name="PC", answers={"q1": "A", "q2": ["A", "C"]})
    policy = GradingPolicy(
        name="pc", correct_points=1.0, incorrect_points=-0.25, partial_credit=True
    )
    sheet = SheetResult(
        sheet_id="s1",
        source_file="s1.png",
        template_name="t",
        fields={
            "q1": FieldReading(field_id="q1", block_name="B", value="ABCDE", confidence=0.5),
            "q2": FieldReading(field_id="q2", block_name="B", value="AC", confidence=0.9),
        },
    )
    grade = ExamGrader(key, policy).grade_sheet(sheet)
    v_map = {v.question_id: v for v in grade.verdicts}
    assert v_map["q1"].verdict == "incorrect"
    assert v_map["q1"].points == -0.25
    assert v_map["q2"].verdict == "correct"
    assert v_map["q2"].points == 1.0


def test_bug22_migrator_raises_clean_value_error_and_expands_custom_labels() -> None:
    with pytest.raises(ValueError, match="missing required key"):
        migrate_legacy_template_dict(
            {"pageDimensions": [800, 1000], "fieldBlocks": {"B1": {"fieldLabels": ["q1"]}}}
        )

    tmpl = migrate_legacy_template_dict(
        {
            "pageDimensions": [800, 1000],
            "bubbleDimensions": [20, 20],
            "customLabels": {"ROLL": ["r1", "r2", "r3"]},
            "fieldBlocks": {
                "ID": {
                    "fieldType": "QTYPE_INT",
                    "origin": [100, 100],
                    "bubblesGap": 30,
                    "labelsGap": 30,
                    "fieldLabels": ["r1..3"],
                }
            },
        }
    )
    assert tmpl.blocks[0].group_as == "ROLL"


def test_bug24_long_pdf_scorecard_auto_paginates() -> None:
    verdicts = [
        QuestionVerdict(
            question_id=f"q{i}",
            marked="A",
            expected="A",
            verdict="correct",
            points=1.0,
        )
        for i in range(1, 211)
    ]
    grade = StudentGrade(
        sheet_id="long_exam",
        source_file="long_exam.pdf",
        total_questions=210,
        correct=210,
        raw_score=210.0,
        max_score=210.0,
        percentage=100.0,
        verdicts=verdicts,
    )
    pdf_bytes = export_pdf_scorecard_bytes(grade, exam_name="210Q Mega Exam")
    pages = load_bytes(pdf_bytes, "scorecard.pdf", dpi=72)
    assert len(pages) == 2
